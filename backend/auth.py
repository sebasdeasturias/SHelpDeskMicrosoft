# backend/auth.py
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import os
import io
import base64
import pyotp
import segno
from dotenv import load_dotenv
from database import get_db
from ratelimit import login_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Configuración sensible cargada desde el .env (raíz del proyecto)
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("Error crítico: No se encontró JWT_SECRET_KEY. Revisa tu archivo .env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
# MFA (TOTP): nombre del emisor que verá el usuario en su app autenticadora y
# vida del token intermedio (entre usuario+contraseña y el código 2FA).
MFA_ISSUER = os.getenv("MFA_ISSUER", "SHelpDesk")
MFA_TOKEN_EXPIRE_MINUTES = 5

# Rate limiting de autenticación (protección contra fuerza bruta / abuso de registro).
# Limpia si el backend corre detrás de un proxy de confianza que fija
# X-Forwarded-For (p.ej. Caddy en docker-compose.prod.yml).
LOGIN_MAX_POR_IP = int(os.getenv("LOGIN_MAX_POR_IP", "10"))
LOGIN_MAX_POR_EMAIL = int(os.getenv("LOGIN_MAX_POR_EMAIL", "5"))
LOGIN_VENTANA_SEG = int(os.getenv("LOGIN_VENTANA_SEG", str(15 * 60)))
REGISTER_MAX_POR_IP = int(os.getenv("REGISTER_MAX_POR_IP", "5"))
REGISTER_VENTANA_SEG = int(os.getenv("REGISTER_VENTANA_SEG", str(60 * 60)))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Modelos Pydantic
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserData(BaseModel):
    id_usuario: int
    nombre: str
    email: str
    rol: str

class MfaVerify(BaseModel):
    mfa_token: str
    code: str

class MfaCode(BaseModel):
    code: str

# Funciones auxiliares
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def _cliente_ip(request: Request) -> str:
    """IP real del cliente. Solo confía en X-Forwarded-For si TRUST_PROXY=true
    (cuando hay un proxy reverso de confianza delante, p.ej. Caddy)."""
    if os.getenv("TRUST_PROXY", "").lower() in ("1", "true", "yes"):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip() or "desconocido"
    return request.client.host if request.client else "desconocido"

async def _revisar_limite_login(request: Request, email: str) -> None:
    ip = _cliente_ip(request)
    if not await login_limiter.allow(f"login:ip:{ip}", LOGIN_MAX_POR_IP, LOGIN_VENTANA_SEG):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de inicio de sesión desde esta IP. Intenta de nuevo más tarde."
        )
    if not await login_limiter.allow(f"login:email:{email.lower()}", LOGIN_MAX_POR_EMAIL, LOGIN_VENTANA_SEG):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos para esta cuenta. Intenta de nuevo más tarde."
        )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def authenticate_user(db: AsyncSession, email: str, password: str):

    from sqlalchemy import text
    
    query = text("SELECT id_usuario, nombre, email, contraseña, rol FROM usuarios WHERE email = :email AND estado = 'activo'")
    result = await db.execute(query, {"email": email})
    user = result.fetchone()
    
    if not user:
        return None
    
    # user es una Row: (id, nombre, email, contraseña_hash, rol)
    if not verify_password(password, user[3]):
        return None
    
    return UserData(id_usuario=user[0], nombre=user[1], email=user[2], rol=user[4])

async def usuario_actual(db: AsyncSession, token: str) -> dict:
    """Decodifica el JWT y lo revalida contra la BD.

    Devuelve los datos REALES del usuario (rol/estado actuales), de modo que
    desactivar una cuenta o cambiarle el rol invalida al instante los tokens ya
    emitidos, sin esperar a que expiren. Lanza 401 si el token es inválido o
    expirado, o si el usuario no existe / no está activo.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, area, estado, mfa_enabled
        FROM usuarios WHERE id_usuario = :id
    """), {"id": user_id})
    u = row.fetchone()
    if not u or u[5] != "activo":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida: el usuario no existe o está inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": u[0],
        "nombre": u[1],
        "email": u[2],
        "sub": u[2],
        "role": u[3],
        "area": u[4],
        "estado": u[5],
        "mfa_enabled": bool(u[6]),
    }


def _crear_mfa_token(user_id: int) -> str:
    """Token intermedio (5 min) entre usuario+contraseña y el código TOTP."""
    return jwt.encode(
        {"scope": "mfa", "user_id": user_id,
         "exp": datetime.utcnow() + timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM)


def _respuesta_token(user: "UserData") -> dict:
    access_token = create_access_token(
        data={"sub": user.email, "role": user.rol, "user_id": user.id_usuario})
    return {"access_token": access_token, "token_type": "bearer", "user": user.dict()}


# Endpoint de Login
@router.post("/login")
async def login(credentials: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    # Rate limiting anti fuerza bruta (por IP y por cuenta).
    await _revisar_limite_login(request, credentials.email)
    # Expirar promociones temporales a administrador: si admin_temporal_hasta
    # ya pasó, el usuario recupera su rol anterior automáticamente.
    await db.execute(text("""
        UPDATE usuarios
        SET rol = rol_anterior, rol_anterior = NULL, admin_temporal_hasta = NULL
        WHERE rol = 'administrador'
          AND rol_anterior IS NOT NULL
          AND admin_temporal_hasta IS NOT NULL
          AND admin_temporal_hasta < NOW()
    """))
    await db.commit()

    user = await authenticate_user(db, credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Si el usuario tiene 2FA activo, no se entrega el token definitivo todavía:
    # se devuelve un reto para completar el segundo factor.
    fila_mfa = await db.execute(text(
        "SELECT mfa_enabled, mfa_secret FROM usuarios WHERE id_usuario = :id"),
        {"id": user.id_usuario})
    mfa = fila_mfa.fetchone()
    if mfa and mfa[0] and mfa[1]:
        return {"mfa_required": True, "mfa_token": _crear_mfa_token(user.id_usuario)}

    return _respuesta_token(user)

# backend/auth.py

class UserRegister(BaseModel):
    nombres: str
    apellidos: str
    email: EmailStr
    area: str
    password: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Registro de nuevo usuario solicitante
    """
    # Rate limiting: evita spam de cuentas desde una misma IP.
    ip = _cliente_ip(request)
    if not await login_limiter.allow(f"register:ip:{ip}", REGISTER_MAX_POR_IP, REGISTER_VENTANA_SEG):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados registros desde esta IP. Intenta de nuevo más tarde."
        )
    
    query = text("SELECT id_usuario FROM usuarios WHERE email = :email")
    result = await db.execute(query, {"email": user_data.email})
    existing_user = result.fetchone()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya está registrado"
        )
    
    # Hashear la contraseña
    hashed_password = pwd_context.hash(user_data.password)
    
    # Combinar nombres y apellidos
    nombre_completo = f"{user_data.nombres} {user_data.apellidos}"
    
    # Insertar nuevo usuario
    insert_query = text("""
        INSERT INTO usuarios (nombre, email, contraseña, rol, area, estado, carga_trabajo, permisos_supervision, permisos_especiales)
        VALUES (:nombre, :email, :contraseña, 'solicitante', :area, 'activo', 0, FALSE, FALSE)
    """)
    
    await db.execute(insert_query, {
        "nombre": nombre_completo,
        "email": user_data.email,
        "contraseña": hashed_password,
        "area": user_data.area
    })
    
    await db.commit()
    
    return {
        "message": "Usuario registrado exitosamente",
        "email": user_data.email,
        "rol": "solicitante"
    }


# ============================================
# MFA (segundo factor TOTP)
# ============================================
def _qr_data_uri(texto: str) -> str:
    """Genera un QR PNG (data URI) para escanear con la app autenticadora."""
    buf = io.BytesIO()
    segno.make(texto).save(buf, kind="png", scale=5, border=2)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@router.post("/mfa/verify")
async def mfa_verify(data: MfaVerify, db: AsyncSession = Depends(get_db)):
    """Segundo paso del login: valida el código TOTP y emite el token real."""
    try:
        payload = jwt.decode(data.mfa_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Reto 2FA inválido o expirado")
    if payload.get("scope") != "mfa":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reto 2FA inválido")
    row = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, mfa_secret, mfa_enabled, estado
        FROM usuarios WHERE id_usuario = :id
    """), {"id": payload.get("user_id")})
    u = row.fetchone()
    if not u or u[6] != "activo" or not u[5] or not u[4]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida")
    if not pyotp.TOTP(u[4]).verify((data.code or "").strip(), valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código 2FA incorrecto")
    return _respuesta_token(UserData(id_usuario=u[0], nombre=u[1], email=u[2], rol=u[3]))


@router.post("/mfa/setup")
async def mfa_setup(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Genera un secreto TOTP (aún sin activar) y devuelve QR y URI otpauth."""
    u = await usuario_actual(db, token)
    secret = pyotp.random_base32()
    await db.execute(text(
        "UPDATE usuarios SET mfa_secret = :s, mfa_enabled = FALSE WHERE id_usuario = :id"),
        {"s": secret, "id": u["user_id"]})
    await db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=u["email"], issuer_name=MFA_ISSUER)
    return {"secret": secret, "otpauth_uri": uri, "qr": _qr_data_uri(uri)}


@router.post("/mfa/enable")
async def mfa_enable(data: MfaCode, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Activa el 2FA tras verificar un código del secreto recién generado."""
    u = await usuario_actual(db, token)
    row = await db.execute(text(
        "SELECT mfa_secret FROM usuarios WHERE id_usuario = :id"), {"id": u["user_id"]})
    secret = row.scalar()
    if not secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Primero inicia la configuración 2FA")
    if not pyotp.TOTP(secret).verify((data.code or "").strip(), valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código 2FA incorrecto")
    await db.execute(text(
        "UPDATE usuarios SET mfa_enabled = TRUE WHERE id_usuario = :id"), {"id": u["user_id"]})
    await db.commit()
    return {"status": "ok", "mfa_enabled": True}


@router.post("/mfa/disable")
async def mfa_disable(data: MfaCode, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Desactiva el 2FA (exige un código válido para evitar bloqueos)."""
    u = await usuario_actual(db, token)
    row = await db.execute(text(
        "SELECT mfa_secret, mfa_enabled FROM usuarios WHERE id_usuario = :id"), {"id": u["user_id"]})
    fila = row.fetchone()
    if not fila or not fila[1] or not fila[0]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El 2FA no está activado")
    if not pyotp.TOTP(fila[0]).verify((data.code or "").strip(), valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código 2FA incorrecto")
    await db.execute(text(
        "UPDATE usuarios SET mfa_enabled = FALSE, mfa_secret = NULL WHERE id_usuario = :id"),
        {"id": u["user_id"]})
    await db.commit()
    return {"status": "ok", "mfa_enabled": False}


@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Obtener usuario actual desde el token, revalidado contra la BD.
    """
    u = await usuario_actual(db, token)
    return {
        "email": u["email"],
        "role": u["role"],
        "user_id": u["user_id"],
        "nombre": u["nombre"],
        "area": u["area"],
        "mfa_enabled": u["mfa_enabled"],
    }