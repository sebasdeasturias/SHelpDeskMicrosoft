# backend/auth.py
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import text
import os
import io
import base64
import ipaddress
import pyotp
import segno
from dotenv import load_dotenv
from database import get_db
from ratelimit import login_limiter
from audit import registrar_log

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

# Cambio obligatorio de contraseña tras un restablecimiento por el administrador.
# El login entrega un ticket restringido (scope "pwd_change") en lugar del token
# de acceso normal. El ticket caduca rápido y solo sirve para /auth/password-change.
PWD_CHANGE_TOKEN_EXPIRE_MINUTES = int(os.getenv("PWD_CHANGE_TOKEN_EXPIRE_MINUTES", "10"))
PWD_CHANGE_MAX_INTENTOS = int(os.getenv("PWD_CHANGE_MAX_INTENTOS", "3"))
PWD_CHANGE_MAX_POR_IP = int(os.getenv("PWD_CHANGE_MAX_POR_IP", "10"))
PWD_CHANGE_VENTANA_SEG = int(os.getenv("PWD_CHANGE_VENTANA_SEG", "900"))

# Rate limiting de autenticación (protección contra fuerza bruta / abuso de registro).
# Limpia si el backend corre detrás de un proxy de confianza que fija
# X-Forwarded-For (p.ej. Caddy en docker-compose.prod.yml).
LOGIN_MAX_POR_IP = int(os.getenv("LOGIN_MAX_POR_IP", "10"))
LOGIN_MAX_POR_EMAIL = int(os.getenv("LOGIN_MAX_POR_EMAIL", "5"))
LOGIN_VENTANA_SEG = int(os.getenv("LOGIN_VENTANA_SEG", str(15 * 60)))
REGISTER_MAX_POR_IP = int(os.getenv("REGISTER_MAX_POR_IP", "5"))
REGISTER_VENTANA_SEG = int(os.getenv("REGISTER_VENTANA_SEG", str(60 * 60)))

# Bloqueo temporal de cuenta por intentos fallidos (persistido en BD, no solo
# en memoria): complementa al rate-limit por IP/email.
LOGIN_MAX_FALLOS = int(os.getenv("LOGIN_MAX_FALLOS", "5"))
LOGIN_BLOQUEO_MIN = int(os.getenv("LOGIN_BLOQUEO_MIN", "15"))

# Rate limit del segundo factor: evita fuerza bruta del código TOTP de 6 dígitos.
MFA_MAX_INTENTOS = int(os.getenv("MFA_MAX_INTENTOS", "5"))
MFA_VENTANA_SEG = int(os.getenv("MFA_VENTANA_SEG", "300"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Modelos Pydantic
class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserData(BaseModel):
    id_usuario: int
    nombre: str
    email: str
    rol: str
    token_version: int = 0

class MfaVerify(BaseModel):
    mfa_token: str
    code: str

class MfaCode(BaseModel):
    code: str

class MfaSetupRequest(BaseModel):
    code: Optional[str] = None

# Funciones auxiliares
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# --- IP real del cliente / proxies de confianza (anti-spoof de X-Forwarded-For) ---
_TRUST_PROXY = os.getenv("TRUST_PROXY", "").lower() in ("1", "true", "yes")
_DEF_TRUSTED_CIDRS = ("127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,"
                      "100.64.0.0/10,::1/128,fc00::/7")


def _parse_cidrs(raw: str):
    redes = []
    for c in raw.split(","):
        c = c.strip()
        if c:
            try:
                redes.append(ipaddress.ip_network(c, strict=False))
            except ValueError:
                continue
    return redes


_REDES_CONFIABLES = _parse_cidrs(os.getenv("TRUSTED_PROXY_CIDRS", _DEF_TRUSTED_CIDRS))


def _ip_confiable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in red for red in _REDES_CONFIABLES)

def _cliente_ip(request: Request) -> str:
    """IP real del cliente.

    Solo confía en X-Forwarded-For con TRUST_PROXY=true. Recorre la cabecera por
    la DERECHA y devuelve la primera IP que NO pertenezca a un proxy de
    confianza (patrón ProxyFix): así un cliente no puede falsear la IP
    inyectando un valor al principio de la cabecera.
    """
    host = request.client.host if request.client else "desconocido"
    if not _TRUST_PROXY:
        return host
    xff = request.headers.get("x-forwarded-for", "")
    partes = [p.strip() for p in xff.split(",") if p.strip()]
    for ip in reversed(partes):
        if not _ip_confiable(ip):
            return ip
    return partes[0] if partes else host

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
    # Los tickets intermedios (2FA y cambio de contraseña) NO son tokens de
    # acceso: no deben servir para llamar al resto de la API.
    if payload.get("scope") in ("mfa", "pwd_change"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no válido para esta operación",
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
        SELECT id_usuario, nombre, email, rol, area, estado, mfa_enabled, token_version,
               debe_cambiar_password
        FROM usuarios WHERE id_usuario = :id
    """), {"id": user_id})
    u = row.fetchone()
    if not u or u[5] != "activo":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida: el usuario no existe o está inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Revocación: si la contraseña se cambió (token_version subió), los tokens
    # emitidos antes dejan de ser válidos inmediatamente.
    if int(payload.get("tv", 0)) != int(u[7] or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida: credenciales actualizadas. Inicia sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Defensa en profundidad: mientras haya un cambio de contraseña pendiente,
    # ningún token de acceso normal es utilizable.
    if u[8]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debes cambiar la contraseña temporal antes de continuar",
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
        data={"sub": user.email, "role": user.rol, "user_id": user.id_usuario,
              "tv": user.token_version})
    return {"access_token": access_token, "token_type": "bearer", "user": user.dict()}


def _crear_pwd_change_token(user_id: int, token_version: int) -> str:
    """Ticket temporal y restringido para cambiar la contraseña obligatoria.

    Lleva `tv` para que quede invalidado si la contraseña se cambia, si se
    agotan los intentos o si el administrador vuelve a restablecerla.
    """
    return jwt.encode(
        {"scope": "pwd_change", "user_id": user_id, "tv": int(token_version),
         "exp": datetime.utcnow() + timedelta(minutes=PWD_CHANGE_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM)


def _respuesta_cambio_password(user: "UserData", intentos: int = 0) -> dict:
    # No se entrega access_token: el usuario todavía no puede usar la API.
    restantes = max(0, PWD_CHANGE_MAX_INTENTOS - int(intentos or 0))
    return {
        "password_change_required": True,
        "pwd_change_token": _crear_pwd_change_token(user.id_usuario, user.token_version),
        "token_type": "bearer",
        "user": user.dict(),
        "intentos_restantes": restantes,
    }


# Endpoint de Login
@router.post("/login")
async def login(credentials: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    # Rate limiting anti fuerza bruta (por IP y por cuenta).
    await _revisar_limite_login(request, credentials.email)
    ip = _cliente_ip(request)
    ua = (request.headers.get("user-agent") or "")[:100] or None
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

    fila_user = await db.execute(text("""
        SELECT id_usuario, nombre, email, contraseña, rol, estado,
               (bloqueado_hasta IS NOT NULL AND bloqueado_hasta > NOW()) AS bloqueado,
               token_version, debe_cambiar_password, intentos_cambio_password
        FROM usuarios WHERE email = :email
    """), {"email": credentials.email})
    u = fila_user.fetchone()

    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales incorrectas o usuario inactivo",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not u:
        await registrar_log("login_fallido", f"email={credentials.email} (no existe)",
                            ip=ip, navegador=ua)
        raise credenciales_invalidas
    if u[6]:
        await registrar_log("login_bloqueado", f"email={credentials.email}",
                            id_usuario=u[0], ip=ip, navegador=ua)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cuenta bloqueada temporalmente por intentos fallidos. Intenta de nuevo más tarde.",
        )
    if u[5] != "activo":
        await registrar_log("login_fallido", f"email={credentials.email} (inactivo)",
                            id_usuario=u[0], ip=ip, navegador=ua)
        raise credenciales_invalidas
    if not verify_password(credentials.password, u[3]):
        # Contador persistente: al superar el máximo, bloquea la cuenta.
        await db.execute(text("""
            UPDATE usuarios
            SET intentos_fallidos = intentos_fallidos + 1,
                bloqueado_hasta = CASE
                    WHEN intentos_fallidos + 1 >= :max
                    THEN NOW() + make_interval(mins => :bloqueo)
                    ELSE bloqueado_hasta END
            WHERE id_usuario = :id
        """), {"max": LOGIN_MAX_FALLOS, "bloqueo": LOGIN_BLOQUEO_MIN, "id": u[0]})
        await db.commit()
        await registrar_log("login_fallido", f"email={credentials.email} (contraseña incorrecta)",
                            id_usuario=u[0], ip=ip, navegador=ua)
        raise credenciales_invalidas

    # Acceso correcto: limpiar contadores y registrar fecha de último acceso.
    await db.execute(text("""
        UPDATE usuarios
        SET intentos_fallidos = 0, bloqueado_hasta = NULL, fecha_ultimo_acceso = NOW()
        WHERE id_usuario = :id
    """), {"id": u[0]})
    await db.commit()
    await registrar_log("login_ok", "autenticación por contraseña",
                        id_usuario=u[0], ip=ip, navegador=ua)

    # Si el administrador restableció la contraseña y ya se agotaron los 3
    # intentos de cambio, no se permite continuar: hace falta un nuevo reset.
    if u[8] and int(u[9] or 0) >= PWD_CHANGE_MAX_INTENTOS:
        await registrar_log("password_cambio_bloqueado",
                            "intentos de cambio agotados en login",
                            id_usuario=u[0], ip=ip, navegador=ua)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Has agotado los 3 intentos para cambiar la contraseña temporal. "
                    "Debes solicitar un nuevo restablecimiento al administrador.")
        )

    user = UserData(id_usuario=u[0], nombre=u[1], email=u[2], rol=u[4],
                    token_version=u[7] or 0)

    # Si el usuario tiene 2FA activo, no se entrega el token definitivo todavía:
    # se devuelve un reto para completar el segundo factor.
    fila_mfa = await db.execute(text(
        "SELECT mfa_enabled, mfa_secret FROM usuarios WHERE id_usuario = :id"),
        {"id": user.id_usuario})
    mfa = fila_mfa.fetchone()
    if mfa and mfa[0] and mfa[1]:
        return {"mfa_required": True, "mfa_token": _crear_mfa_token(user.id_usuario)}

    if u[8]:
        return _respuesta_cambio_password(user, u[9])
    return _respuesta_token(user)

# backend/auth.py

class UserRegister(BaseModel):
    nombres: str = Field(..., min_length=1, max_length=100)
    apellidos: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    area: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)

class PasswordResetRequest(BaseModel):
    email: EmailStr
    motivo: Optional[str] = Field(None, max_length=500)

class PasswordChange(BaseModel):
    password_temporal: str = Field(..., min_length=1, max_length=128)
    password_nueva: str = Field(..., min_length=8, max_length=128)
    password_nueva2: str = Field(..., min_length=8, max_length=128)

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
        # Mensaje GENÉRICO a propósito: no confirma si el correo existe
        # (evita enumeración de usuarios; hallazgo A3).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo completar el registro. Revisa los datos e inténtalo de nuevo."
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

    await registrar_log("registro", f"email={user_data.email}",
                        ip=ip, navegador=(request.headers.get("user-agent") or "")[:100] or None)
    return {
        "message": "Usuario registrado exitosamente",
        "email": user_data.email,
        "rol": "solicitante"
    }


# ============================================
# RESTABLECIMIENTO DE CONTRASEÑA (solicitud presencial)
# ============================================
# El sistema no envía contraseñas por correo ni SMS: el usuario registra la
# solicitud y el ADMINISTRADOR valida su identidad en persona antes de asignar
# una contraseña temporal. La respuesta es siempre la misma para no revelar si
# el correo existe (anti-enumeración).
_PW_RESET_RESPUESTA = {
    "status": "ok",
    "mensaje": ("Si el correo pertenece a una cuenta activa, la solicitud quedó "
                "registrada. Acude personalmente a TI con tu documento de "
                "identidad para que el administrador valide tu identidad.")
}


@router.post("/password-reset-request", status_code=status.HTTP_202_ACCEPTED)
async def password_reset_request(data: PasswordResetRequest, request: Request,
                                 db: AsyncSession = Depends(get_db)):
    """Registra una solicitud de restablecimiento para validación presencial."""
    ip = _cliente_ip(request)
    ua = (request.headers.get("user-agent") or "")[:100] or None

    # Límites anti-abuso: por IP y por correo (evita inundar el panel del admin).
    if not await login_limiter.allow(f"pwreset:ip:{ip}", 5, 3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes desde esta IP. Inténtalo de nuevo más tarde."
        )
    email = str(data.email).strip().lower()
    if not await login_limiter.allow(f"pwreset:email:{email}", 3, 3600):
        return _PW_RESET_RESPUESTA

    result = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol
        FROM usuarios
        WHERE lower(email) = :email AND estado = 'activo'
    """), {"email": email})
    u = result.fetchone()
    if not u:
        # No se crea nada, pero la respuesta es idéntica (anti-enumeración).
        return _PW_RESET_RESPUESTA

    motivo = (data.motivo or "").strip()[:500] or None
    # Una sola solicitud abierta por usuario (índice único parcial).
    await db.execute(text("""
        INSERT INTO solicitud_password
            (id_usuario, email, nombre, rol_solicitante, motivo, origen_ip)
        VALUES (:id, :email, :nombre, :rol, :motivo, :ip)
        ON CONFLICT (id_usuario) WHERE estado IN ('pendiente', 'identidad_validada')
        DO NOTHING
    """), {
        "id": u[0], "email": u[2], "nombre": u[1], "rol": u[3],
        "motivo": motivo, "ip": ip,
    })
    await db.commit()

    await registrar_log("password_reset_solicitado",
                        f"usuario={u[0]} email={u[2]}",
                        id_usuario=u[0], ip=ip, navegador=ua)
    return _PW_RESET_RESPUESTA


# ============================================
# CAMBIO OBLIGATORIO DE CONTRASEÑA
# ============================================
@router.post("/password-change")
async def password_change(data: PasswordChange, request: Request,
                          token: str = Depends(oauth2_scheme),
                          db: AsyncSession = Depends(get_db)):
    """Cambia la contraseña temporal usando el ticket restringido del login.

    No acepta tokens de acceso normales: exige `scope="pwd_change"`. Así, hasta
    que el usuario no cambie la contraseña, no puede usar el resto de la API.
    """
    ip = _cliente_ip(request)
    ua = (request.headers.get("user-agent") or "")[:100] or None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Ticket de cambio inválido o expirado")
    if payload.get("scope") != "pwd_change":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Ticket de cambio inválido")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Ticket de cambio inválido")

    # Límite de tasa adicional (el límite real de intentos vive en la BD).
    if not await login_limiter.allow(f"pwdchange:ip:{ip}", PWD_CHANGE_MAX_POR_IP, PWD_CHANGE_VENTANA_SEG):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demasiados intentos. Espera unos minutos.")
    if not await login_limiter.allow(f"pwdchange:user:{user_id}", PWD_CHANGE_MAX_POR_IP, PWD_CHANGE_VENTANA_SEG):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demasiados intentos. Espera unos minutos.")

    row = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, contraseña, estado,
               token_version, debe_cambiar_password, intentos_cambio_password
        FROM usuarios WHERE id_usuario = :id
    """), {"id": user_id})
    u = row.fetchone()
    if not u or u[5] != "activo":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida")
    if int(payload.get("tv", 0)) != int(u[6] or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Ticket expirado. Inicia sesión de nuevo con la contraseña temporal.")
    if not u[7]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No hay un cambio de contraseña pendiente")
    if int(u[8] or 0) >= PWD_CHANGE_MAX_INTENTOS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"mensaje": ("Has agotado los 3 intentos. Solicita un nuevo "
                                "restablecimiento al administrador."),
                    "intentos_restantes": 0, "bloqueado": True}
        )

    # Errores de validación de la nueva contraseña: no consumen intentos.
    if data.password_nueva != data.password_nueva2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Las contraseñas nuevas no coinciden")
    if verify_password(data.password_nueva, u[4]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="La nueva contraseña debe ser distinta de la temporal")

    # La contraseña temporal sí se compara contra el hash de la BD. Un fallo
    # consume uno de los 3 intentos y, al llegar a 0, invalida el ticket.
    if not verify_password(data.password_temporal, u[4]):
        res = await db.execute(text("""
            UPDATE usuarios
            SET intentos_cambio_password = intentos_cambio_password + 1,
                token_version = CASE
                    WHEN intentos_cambio_password + 1 >= :max
                    THEN token_version + 1
                    ELSE token_version END
            WHERE id_usuario = :id
            RETURNING intentos_cambio_password
        """), {"max": PWD_CHANGE_MAX_INTENTOS, "id": user_id})
        intentos = int(res.scalar() or 0)
        await db.commit()
        restantes = max(0, PWD_CHANGE_MAX_INTENTOS - intentos)
        await registrar_log("password_cambio_fallido",
                            f"intentos={intentos}", id_usuario=user_id,
                            ip=ip, navegador=ua)
        if restantes <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"mensaje": ("Has agotado los 3 intentos. Solicita un nuevo "
                                    "restablecimiento al administrador."),
                        "intentos_restantes": 0, "bloqueado": True}
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"mensaje": "La contraseña temporal no coincide",
                    "intentos_restantes": restantes, "bloqueado": False}
        )

    # Cambio válido: nueva contraseña, se limpia el flag, se reinician intentos
    # y se revocan todos los JWT previos (incluido el ticket actual).
    res = await db.execute(text("""
        UPDATE usuarios
        SET contraseña = :pwd,
            debe_cambiar_password = FALSE,
            intentos_cambio_password = 0,
            token_version = token_version + 1,
            intentos_fallidos = 0,
            bloqueado_hasta = NULL,
            fecha_ultimo_acceso = NOW()
        WHERE id_usuario = :id
        RETURNING token_version
    """), {"pwd": pwd_context.hash(data.password_nueva), "id": user_id})
    nuevo_tv = int(res.scalar() or 0)
    await db.commit()

    await registrar_log("password_cambio_ok", "", id_usuario=user_id,
                        ip=ip, navegador=ua)
    usuario = UserData(id_usuario=u[0], nombre=u[1], email=u[2], rol=u[3],
                       token_version=nuevo_tv)
    respuesta = _respuesta_token(usuario)
    respuesta["password_change_completed"] = True
    return respuesta


# ============================================
# MFA (segundo factor TOTP)
# ============================================
def _qr_data_uri(texto: str) -> str:
    """Genera un QR PNG (data URI) para escanear con la app autenticadora."""
    buf = io.BytesIO()
    segno.make(texto).save(buf, kind="png", scale=5, border=2)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@router.post("/mfa/verify")
async def mfa_verify(data: MfaVerify, request: Request, db: AsyncSession = Depends(get_db)):
    """Segundo paso del login: valida el código TOTP y emite el token real."""
    ip = _cliente_ip(request)
    ua = (request.headers.get("user-agent") or "")[:100] or None
    try:
        payload = jwt.decode(data.mfa_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Reto 2FA inválido o expirado")
    if payload.get("scope") != "mfa":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reto 2FA inválido")

    # Rate limit del segundo factor (fuerza bruta del TOTP de 6 dígitos).
    user_id = payload.get("user_id")
    if not await login_limiter.allow(f"mfa:verify:{user_id}", MFA_MAX_INTENTOS, MFA_VENTANA_SEG):
        await registrar_log("mfa_fallido", "rate limit del 2FA", id_usuario=user_id, ip=ip, navegador=ua)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Demasiados intentos de 2FA. Espera unos minutos.")

    row = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, mfa_secret, mfa_enabled, estado, token_version,
               debe_cambiar_password, intentos_cambio_password
        FROM usuarios WHERE id_usuario = :id
    """), {"id": user_id})
    u = row.fetchone()
    if not u or u[6] != "activo" or not u[5] or not u[4]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida")
    if not pyotp.TOTP(u[4]).verify((data.code or "").strip(), valid_window=1):
        await registrar_log("mfa_fallido", "código 2FA incorrecto", id_usuario=u[0], ip=ip, navegador=ua)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código 2FA incorrecto")
    if u[8] and int(u[9] or 0) >= PWD_CHANGE_MAX_INTENTOS:
        await registrar_log("password_cambio_bloqueado",
                            "intentos de cambio agotados tras 2FA",
                            id_usuario=u[0], ip=ip, navegador=ua)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Has agotado los 3 intentos para cambiar la contraseña temporal. "
                    "Debes solicitar un nuevo restablecimiento al administrador.")
        )
    await registrar_log("login_ok", "autenticación con 2FA", id_usuario=u[0], ip=ip, navegador=ua)
    usuario = UserData(id_usuario=u[0], nombre=u[1], email=u[2], rol=u[3],
                       token_version=u[7] or 0)
    if u[8]:
        return _respuesta_cambio_password(usuario, u[9])
    return _respuesta_token(usuario)


@router.post("/mfa/setup")
async def mfa_setup(data: Optional[MfaSetupRequest] = None,
                    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Genera un secreto TOTP (aún sin activar) y devuelve QR y URI otpauth.
    Si el 2FA ya está activo, exige el código vigente para regenerarlo: evita que
    un token robado desactive silenciosamente el segundo factor."""
    u = await usuario_actual(db, token)
    fila = (await db.execute(text(
        "SELECT mfa_enabled, mfa_secret FROM usuarios WHERE id_usuario = :id"),
        {"id": u["user_id"]})).fetchone()
    if fila and fila[0] and fila[1]:
        codigo = (data.code if data else "") or ""
        if not codigo or not pyotp.TOTP(fila[1]).verify(codigo.strip(), valid_window=1):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Confirma tu código 2FA actual para reconfigurarlo")
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


@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Cierra la sesión revocando los JWT del usuario (sube token_version)."""
    u = await usuario_actual(db, token)
    await db.execute(text(
        "UPDATE usuarios SET token_version = token_version + 1 WHERE id_usuario = :id"),
        {"id": u["user_id"]})
    await db.commit()
    await registrar_log("logout", None, id_usuario=u["user_id"])
    return {"status": "ok"}


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

# ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
#█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
# ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
#  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
#████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
# ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
#  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 