# backend/auth.py
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import os
from dotenv import load_dotenv
from database import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Configuración sensible cargada desde el .env (raíz del proyecto)
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("Error crítico: No se encontró JWT_SECRET_KEY. Revisa tu archivo .env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

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

# Funciones auxiliares
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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

# Endpoint de Login
@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, credentials.email, credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user.email, "role": user.rol, "user_id": user.id_usuario}
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user.dict()
    )

# backend/auth.py

class UserRegister(BaseModel):
    nombres: str
    apellidos: str
    email: EmailStr
    area: str
    password: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Registro de nuevo usuario solicitante
    """
    
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
@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Obtener usuario actual desde el token
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: int = payload.get("user_id")
        
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        
        # Obtener información adicional del usuario
        result = await db.execute(text("""
            SELECT nombre, area FROM usuarios WHERE id_usuario = :user_id
        """), {"user_id": user_id})
        
        user_row = result.fetchone()
        
        return {
            "email": email,
            "role": role,
            "user_id": user_id,
            "nombre": user_row[0] if user_row else email,
            "area": user_row[1] if user_row else None
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid"
        )