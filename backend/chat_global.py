# backend/chat_global.py
# Chat global del HelpDesk: todos los roles autenticados (solicitante incluido)
# pueden conversar en un canal común. A diferencia del chat IA (agente/cohorte
# de soporte), aquí NO hay restricción de rol: solo se exige sesión válida.
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import SECRET_KEY, ALGORITHM, oauth2_scheme
from ratelimit import chat_limiter

router = APIRouter(prefix="/chat-global", tags=["Chat Global"])

LIMITE_MENSAJE = 1000
# Rate limit por usuario: evita flood del canal (el chat IA ya usa el mismo
# limiter con otra clave; las ventanas son independientes por clave).
CHAT_GLOBAL_MAX_POR_MIN = 20


class MensajeGlobalRequest(BaseModel):
    mensaje: str

    @field_validator("mensaje")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El mensaje no puede estar vacío")
        if len(v) > LIMITE_MENSAJE:
            raise ValueError(f"El mensaje no puede superar {LIMITE_MENSAJE} caracteres")
        return v


def _payload_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _fila_a_dict(r) -> dict:
    return {
        "id_mensaje": r[0],
        "user_id": r[1],
        "nombre": r[2],
        "rol": r[3],
        "area": r[4],
        "mensaje": r[5],
        "fecha": r[6].isoformat() if r[6] else None,
    }


@router.get("/mensajes")
async def listar_mensajes(
    since_id: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Historial del chat global. El frontend hace polling con since_id:
    solo llegan los mensajes nuevos (barato en BD y red)."""
    _payload_token(token)

    limit = max(1, min(limit, 100))
    # Primer arranque: últimos `limit` mensajes en orden cronológico.
    # Polling (since_id > 0): solo lo nuevo.
    if since_id > 0:
        result = await db.execute(text("""
            SELECT m.id_mensaje, u.id_usuario, u.nombre, u.rol, u.area, m.mensaje, m.fecha
            FROM mensaje_chat_global m
            JOIN usuarios u ON u.id_usuario = m.id_usuario
            WHERE m.id_mensaje > :since
            ORDER BY m.id_mensaje ASC
            LIMIT :limit
        """), {"since": since_id, "limit": limit})
    else:
        result = await db.execute(text("""
            SELECT id_mensaje, user_id, nombre, rol, area, mensaje, fecha FROM (
                SELECT m.id_mensaje, u.id_usuario AS user_id, u.nombre, u.rol, u.area, m.mensaje, m.fecha
                FROM mensaje_chat_global m
                JOIN usuarios u ON u.id_usuario = m.id_usuario
                ORDER BY m.id_mensaje DESC
                LIMIT :limit
            ) ultimos
            ORDER BY id_mensaje ASC
        """), {"limit": limit})

    return [_fila_a_dict(r) for r in result.fetchall()]


@router.post("/mensajes", status_code=status.HTTP_201_CREATED)
async def enviar_mensaje(
    data: MensajeGlobalRequest,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    payload = _payload_token(token)
    user_id = payload.get("user_id")

    # Flood control por usuario (independiente del cupo del chat IA).
    if not await chat_limiter.allow(f"chat-global:user:{user_id}", CHAT_GLOBAL_MAX_POR_MIN, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Estás enviando mensajes demasiado rápido. Espera unos segundos."
        )

    # El usuario debe seguir activo (un usuario desactivado no escribe).
    r_user = await db.execute(text("""
        SELECT id_usuario FROM usuarios WHERE id_usuario = :id AND estado = 'activo'
    """), {"id": user_id})
    if not r_user.fetchone():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo")

    result = await db.execute(text("""
        INSERT INTO mensaje_chat_global (id_usuario, mensaje, fecha)
        VALUES (:user_id, :mensaje, NOW())
        RETURNING id_mensaje, fecha
    """), {"user_id": user_id, "mensaje": data.mensaje})
    id_mensaje, fecha = result.fetchone()

    fila = await db.execute(text("""
        SELECT m.id_mensaje, u.id_usuario, u.nombre, u.rol, u.area, m.mensaje, m.fecha
        FROM mensaje_chat_global m JOIN usuarios u ON u.id_usuario = m.id_usuario
        WHERE m.id_mensaje = :id
    """), {"id": id_mensaje})
    mensaje = _fila_a_dict(fila.fetchone())

    await db.commit()
    return mensaje
