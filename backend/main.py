from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from auth import router as auth_router
from tickets import router as tickets_router
from chat_ai import router as chat_router
from coordinator import router as coordinator_router

app = FastAPI(
    title="HelpDesk API",
    description="API para el Sistema HelpDesk con IA y RAG",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(tickets_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(coordinator_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "HelpDesk API is running successfully!", "status": "ok"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}