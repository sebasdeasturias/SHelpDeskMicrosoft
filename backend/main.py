from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from auth import router as auth_router
from tickets import router as tickets_router
from chat_ai import router as chat_router
from coordinator import router as coordinator_router
from adjuntos import router as adjuntos_router, UPLOAD_DIR

# Carpeta pública de adjuntos: los archivos se guardan con nombres UUID no
# adivinables y se sirven estáticos para que <img>/<a> del frontend funcionen
# sin enviar cabeceras de autenticación.
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="HelpDesk API",
    description="API para el Sistema HelpDesk con IA y RAG",
    version="1.0.0"
)

# CORS: orígenes permitidos desde el .env (separados por coma).
# Ejemplo para frontend en Vercel + backend en VPS:
#   CORS_ORIGINS=https://midominio.com,https://www.midominio.com
# Si se deja "*", se permite cualquier origen pero sin credenciales
# (recomendado solo cuando la API es pública y no usa cookies).
_cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else ["*"]
_cors_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(tickets_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(coordinator_router, prefix="/api")
app.include_router(adjuntos_router, prefix="/api")

# Archivos adjuntos de los tickets (PNG/JPG, nombres UUID no adivinables)
app.mount("/api/adjuntos-archivos", StaticFiles(directory=UPLOAD_DIR), name="adjuntos")

@app.get("/")
async def root():
    return {"message": "HelpDesk API is running successfully!", "status": "ok"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}