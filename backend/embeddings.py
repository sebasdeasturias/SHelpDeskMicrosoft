# backend/embeddings.py
# Cliente de embeddings (Ollama) para el RAG: bge-m3 -> pgvector (similitud coseno)
import os
import httpx
from sqlalchemy import text

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")


async def generar_embedding(texto: str) -> list[float]:
    """Genera el embedding de un texto con el modelo configurado (bge-m3, 1024 dims)."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/embed",
            json={
                "model": EMBEDDING_MODEL,
                "input": texto,
                "keep_alive": "30m",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["embeddings"][0]


def a_vector_sql(vec: list[float]) -> str:
    """Formato textual '[0.1,0.2,...]' que pgvector acepta con cast ::vector."""
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


async def indexar_ticket(db, id_solicitud: int, asunto: str, descripcion: str = "") -> bool:
    """Genera y almacena (upsert) el embedding de un ticket para el modelo actual."""
    texto = f"{asunto}. {descripcion or ''}".strip()
    if not texto:
        return False
    vec = await generar_embedding(texto)
    qvec = a_vector_sql(vec)
    await db.execute(text("""
        DELETE FROM embedding_vector
        WHERE id_solicitud = :id AND modelo_embedding = :modelo
    """), {"id": id_solicitud, "modelo": EMBEDDING_MODEL})
    await db.execute(text("""
        INSERT INTO embedding_vector (id_solicitud, embedding, modelo_embedding)
        VALUES (:id, CAST(:vec AS vector), :modelo)
    """), {"id": id_solicitud, "vec": qvec, "modelo": EMBEDDING_MODEL})
    await db.commit()
    return True
