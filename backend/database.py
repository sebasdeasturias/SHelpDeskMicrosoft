# backend/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv
import os

# 1. Cargar el archivo .env
load_dotenv()

# 2. Leer la variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Si no existe, romper la aplicación inmediatamente con un error claro
if not DATABASE_URL:
    raise ValueError("Error crítico: No se encontró DATABASE_URL. Revisa tu archivo .env")

# 4. Crear el motor
engine = create_async_engine(DATABASE_URL, echo=False)

# 5. Sesiones y Base
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()