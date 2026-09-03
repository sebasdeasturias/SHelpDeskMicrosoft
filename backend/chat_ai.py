# backend/chat_ai.py
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import os
import time

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import SECRET_KEY, ALGORITHM, oauth2_scheme
from ratelimit import chat_limiter

router = APIRouter(prefix="/chat", tags=["Chat IA"])

# Configuración
N8N_CHAT_URL = os.getenv("N8N_CHAT_URL")
N8N_URL = os.getenv("N8N_URL", "http://localhost:5678")
DEFAULT_MODEL = "llama3.2:3b"

SYSTEM_PROMPT = """Eres un asistente técnico experto en soporte IT del sistema HelpDesk realizado por S.Morales.
Tu trabajo es ayudar a los agentes de soporte a resolver tickets de forma rápida y eficiente.
Responde en español, de manera clara, concisa y profesional.
Si te dan contexto de un ticket, úsalo para dar una solución específica.
Si no sabes algo, dilo honestamente y sugiere alternativas. NO MANDES CÓDIGOS O COMANDOS QUE PUEDAN DAÑAR EL SISTEMA.
No inventes información. Si no tienes suficiente contexto, pide más detalles al agente."""


# ============================================
# MODELOS PYDANTIC
# ============================================
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    mensaje: str
    modelo: Optional[str] = DEFAULT_MODEL
    historial: Optional[List[ChatMessage]] = []
    ticket_id: Optional[int] = None


class ChatResponse(BaseModel):
    respuesta: str
    modelo: str
    tokens: Optional[Dict[str, Any]] = None
    ticket_contexto: Optional[str] = None
    tiempo_ms: int = 0


# ============================================
# FUNCIONES AUXILIARES
# ============================================
def verify_token(token: str) -> dict:
    """Valida el token JWT y devuelve el payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_ticket_context(db: AsyncSession, ticket_id: int) -> Optional[str]:
    """Obtiene el contexto completo de un ticket: datos del ticket,
    solicitante, agente asignado y análisis de la IA local."""
    query = text("""
        SELECT s.id_solicitud, s.asunto, s.descripcion, s.estado,
               c.nombre AS categoria, p.nivel AS prioridad,
               sol.nombre AS sol_nombre, sol.email AS sol_email, sol.area AS sol_area,
               ag.nombre AS agente_nombre,
               ci.categoria_ia, ci.prioridad_ia, ci.confianza, ci.modelo_ia
        FROM solicitud s
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
        LEFT JOIN usuarios sol ON s.id_solicitante = sol.id_usuario
        LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
        LEFT JOIN clasificacion_ia ci ON ci.id_solicitud = s.id_solicitud
        WHERE s.id_solicitud = :id
        ORDER BY ci.fecha_clasificacion DESC NULLS LAST
        LIMIT 1
    """)
    result = await db.execute(query, {"id": ticket_id})
    t = result.fetchone()
    if not t:
        return None

    partes = [
        f"[Ticket #{t[0]}] Asunto: {t[1]} | Estado: {t[3]} | "
        f"Categoría: {t[4] or 'N/A'} | Prioridad: {t[5] or 'N/A'}",
        f"Descripción: {t[2]}",
        f"Solicitante: {t[6] or 'N/A'} ({t[7] or 'sin email'}) | Área: {t[8] or 'N/A'}",
        f"Agente asignado: {t[9] or 'Sin asignar'}"
    ]

    if t[10] or t[11]:
        confianza = f"{round(float(t[12]) * 100, 1)}%" if t[12] is not None else "N/A"
        partes.append(
            f"Análisis IA local ({t[13] or 'modelo desconocido'}): "
            f"categoría sugerida={t[10] or 'N/A'}, prioridad sugerida={t[11] or 'N/A'}, "
            f"confianza={confianza}"
        )

    return "\n".join(partes)


async def log_ai_interaction(
    db: AsyncSession, user_id: int, prompt: str, response: str,
    tokens: int, time_ms: int, ticket_id: Optional[int]
):
    """Guarda el log de la interacción con IA en la tabla log_ia."""
    try:
        query = text("""
            INSERT INTO log_ia (accion, prompt, respuesta_ia, tokens_usados, tiempo_ejecucion_ms, id_solicitud, id_usuario)
            VALUES ('chat_soporte', :prompt, :respuesta, :tokens, :tiempo_ms, :id_solicitud, :id_usuario)
        """)
        await db.execute(query, {
            "prompt": prompt[:2000],
            "respuesta": response[:2000],
            "tokens": tokens,
            "tiempo_ms": time_ms,
            "id_solicitud": ticket_id,
            "id_usuario": user_id
        })
        await db.commit()
    except Exception as e:
        print(f"⚠️ Error guardando log IA: {e}")


# ============================================
# ENDPOINTS
# ============================================
@router.get("/health")
async def chat_health():
    """Verifica que n8n esté accesible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Solo verificamos que el puerto responda
            response = await client.get(f"{N8N_URL}/healthz")
            return {"status": "ok", "n8n": "accessible"}
    except Exception:
        return {"status": "warning", "n8n": f"no accesible en {N8N_URL}"}


@router.post("", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint principal de chat con IA.
    Flujo: Frontend → Backend → n8n → Ollama → respuesta
    """
    # 1. Validar token
    payload = verify_token(token)
    user_id = payload.get("user_id")
    user_role = payload.get("role")

    # Solo personal de soporte usa el chat (evita que un solicitante autenticado
    # consuma recursos de Ollama a voluntad).
    if user_role not in ("agente", "coordinador", "administrador"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El chat con IA está disponible solo para personal de soporte"
        )

    # 1b. Rate limiting por usuario (protege a Ollama de uso excesivo).
    if not await chat_limiter.allow(f"chat:user:{user_id}", 30, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados mensajes por minuto. Espera unos segundos antes de continuar."
        )

    # 2. Si hay ticket adjunto, obtener contexto de la BD
    ticket_contexto = None
    mensaje_completo = request.mensaje
    if request.ticket_id:
        contexto = await get_ticket_context(db, request.ticket_id)
        if contexto:
            ticket_contexto = contexto
            mensaje_completo = f"{contexto}\n\nPregunta del agente: {request.mensaje}"

    # 3. Determinar el modelo: explícito → configuracion_ia (panel admin) → DEFAULT_MODEL
    modelo_final = request.modelo
    if not modelo_final:
        r_modelo = await db.execute(
            text("SELECT valor FROM configuracion_ia WHERE clave = 'modelo_chat'")
        )
        fila_modelo = r_modelo.first()
        modelo_final = fila_modelo[0] if fila_modelo and fila_modelo[0] else DEFAULT_MODEL

    # 3b. Parámetros de generación configurables por el administrador (configuracion_ia)
    r_params = await db.execute(text("""
        SELECT clave, valor FROM configuracion_ia
        WHERE clave IN ('temperatura', 'num_predict', 'top_p')
    """))
    params = {row[0]: row[1] for row in r_params.fetchall()}
    try:
        temperatura = float(params.get("temperatura", 0.8))
    except (TypeError, ValueError):
        temperatura = 0.8
    try:
        num_predict = int(float(params.get("num_predict", 512)))
    except (TypeError, ValueError):
        num_predict = 512
    try:
        top_p = float(params.get("top_p", 0.9))
    except (TypeError, ValueError):
        top_p = 0.9

    # 4. Preparar payload para n8n
    n8n_payload = {
        "mensaje": mensaje_completo,
        "modelo": modelo_final,
        "historial": [msg.dict() for msg in request.historial] if request.historial else [],
        "sistema": SYSTEM_PROMPT,
        "temperatura": temperatura,
        "num_predict": num_predict,
        "top_p": top_p,
    }

    # 5. Llamar a n8n
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(N8N_CHAT_URL, json=n8n_payload)
            response.raise_for_status()
            n8n_data = response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar con n8n. Verifica que esté corriendo en {N8N_URL}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout: la IA tardó demasiado en responder"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"n8n devolvió un error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado: {str(e)}"
        )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 6. Extraer respuesta de n8n
    respuesta = n8n_data.get("respuesta", "Sin respuesta del modelo.")
    tokens_data = n8n_data.get("tokens", {})
    tokens_usados = tokens_data.get("tokens_generados", 0)

    # 7. Guardar log en la BD (no bloquea si falla)
    await log_ai_interaction(
        db, user_id, request.mensaje, respuesta,
        tokens_usados, elapsed_ms, request.ticket_id
    )

    # 8. Devolver respuesta al frontend
    return ChatResponse(
        respuesta=respuesta,
        modelo=modelo_final,
        tokens=tokens_data,
        ticket_contexto=ticket_contexto,
        tiempo_ms=elapsed_ms
    )