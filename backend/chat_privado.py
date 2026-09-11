# backend/chat_privado.py
# Chat privado 1 a 1 entre personal interno (agente, coordinador, administrador).
# Los solicitantes NO tienen acceso: no pueden listar contactos ni leer/escribir
# conversaciones. Toda lectura filtra por pertenencia (emisor o receptor = yo),
# de modo que nunca se expone un mensaje ajeno.
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import oauth2_scheme, usuario_actual
from ratelimit import chat_limiter

router = APIRouter(prefix="/chat-privado", tags=["Chat Privado"])

ROLES_INTERNOS = ("agente", "coordinador", "administrador")
LIMITE_MENSAJE = 1000
CHAT_PRIVADO_MAX_POR_MIN = 20


class MensajePrivadoRequest(BaseModel):
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


async def _payload_interno(db: AsyncSession, token: str) -> dict:
    """Revalida el token y exige rol de personal interno."""
    payload = await usuario_actual(db, token)
    if payload.get("role") not in ROLES_INTERNOS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El chat privado está disponible solo para personal de soporte",
        )
    return payload


async def _validar_destino(db: AsyncSession, otro_id: int, yo_id: int) -> dict:
    """Comprueba que el destinatario existe, está activo y es personal interno."""
    if otro_id == yo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes abrir un chat privado contigo mismo",
        )
    r = await db.execute(text("""
        SELECT id_usuario, nombre, rol, area, estado
        FROM usuarios WHERE id_usuario = :id
    """), {"id": otro_id})
    u = r.fetchone()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El usuario no existe")
    if u[4] != "activo" or u[2] not in ROLES_INTERNOS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no está disponible para chat privado",
        )
    return {"id_usuario": u[0], "nombre": u[1], "rol": u[2], "area": u[3]}


def _msg_a_dict(r) -> dict:
    return {
        "id_mensaje": r[0],
        "id_emisor": r[1],
        "id_receptor": r[2],
        "mensaje": r[3],
        "leido": bool(r[4]),
        "fecha": r[5].isoformat() if r[5] else None,
    }


@router.get("/contactos")
async def listar_contactos(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Personal interno activo con quien se puede chatear, junto al último
    mensaje de la conversación y el número de no leídos."""
    yo = (await _payload_interno(db, token))["user_id"]

    result = await db.execute(text("""
        SELECT u.id_usuario, u.nombre, u.rol, u.area,
               no_leidos.total,
               ult.mensaje, ult.fecha
        FROM usuarios u
        LEFT JOIN LATERAL (
            SELECT count(*) AS total
            FROM mensaje_chat_privado m
            WHERE m.id_emisor = u.id_usuario
              AND m.id_receptor = :yo
              AND m.leido = FALSE
        ) no_leidos ON TRUE
        LEFT JOIN LATERAL (
            SELECT m.mensaje, m.fecha
            FROM mensaje_chat_privado m
            WHERE (m.id_emisor = u.id_usuario AND m.id_receptor = :yo)
               OR (m.id_emisor = :yo AND m.id_receptor = u.id_usuario)
            ORDER BY m.id_mensaje DESC
            LIMIT 1
        ) ult ON TRUE
        WHERE u.estado = 'activo'
          AND u.rol IN ('agente', 'coordinador', 'administrador')
          AND u.id_usuario <> :yo
        ORDER BY ult.fecha DESC NULLS LAST, u.nombre ASC
    """), {"yo": yo})

    return [
        {
            "id_usuario": r[0],
            "nombre": r[1],
            "rol": r[2],
            "area": r[3],
            "no_leidos": int(r[4] or 0),
            "ultimo_mensaje": r[5],
            "ultima_fecha": r[6].isoformat() if r[6] else None,
        }
        for r in result.fetchall()
    ]


@router.get("/no-leidos")
async def contar_no_leidos(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Total de mensajes privados sin leer (badge del FAB)."""
    yo = (await _payload_interno(db, token))["user_id"]
    r = await db.execute(text("""
        SELECT count(*) FROM mensaje_chat_privado
        WHERE id_receptor = :yo AND leido = FALSE
    """), {"yo": yo})
    return {"total": int(r.scalar() or 0)}


@router.get("/conversacion/{otro_id}")
async def ver_conversacion(
    otro_id: int,
    since_id: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Mensajes entre el usuario y `otro_id`. El polling usa since_id.
    Al abrir/consultar, los mensajes recibidos se marcan como leídos."""
    yo = (await _payload_interno(db, token))["user_id"]
    await _validar_destino(db, otro_id, yo)

    # Marca como leídos los mensajes que me envió este contacto.
    await db.execute(text("""
        UPDATE mensaje_chat_privado SET leido = TRUE
        WHERE id_emisor = :otro AND id_receptor = :yo AND leido = FALSE
    """), {"otro": otro_id, "yo": yo})

    limit = max(1, min(limit, 100))
    if since_id > 0:
        result = await db.execute(text("""
            SELECT id_mensaje, id_emisor, id_receptor, mensaje, leido, fecha
            FROM mensaje_chat_privado
            WHERE id_mensaje > :since
              AND ((id_emisor = :yo AND id_receptor = :otro)
                OR (id_emisor = :otro AND id_receptor = :yo))
            ORDER BY id_mensaje ASC
            LIMIT :limit
        """), {"since": since_id, "yo": yo, "otro": otro_id, "limit": limit})
    else:
        result = await db.execute(text("""
            SELECT id_mensaje, id_emisor, id_receptor, mensaje, leido, fecha FROM (
                SELECT id_mensaje, id_emisor, id_receptor, mensaje, leido, fecha
                FROM mensaje_chat_privado
                WHERE (id_emisor = :yo AND id_receptor = :otro)
                   OR (id_emisor = :otro AND id_receptor = :yo)
                ORDER BY id_mensaje DESC
                LIMIT :limit
            ) ultimos
            ORDER BY id_mensaje ASC
        """), {"yo": yo, "otro": otro_id, "limit": limit})

    await db.commit()
    return [_msg_a_dict(r) for r in result.fetchall()]


@router.post("/conversacion/{otro_id}", status_code=status.HTTP_201_CREATED)
async def enviar_mensaje(
    otro_id: int,
    data: MensajePrivadoRequest,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    yo = (await _payload_interno(db, token))["user_id"]
    await _validar_destino(db, otro_id, yo)

    if not await chat_limiter.allow(f"chat-privado:user:{yo}", CHAT_PRIVADO_MAX_POR_MIN, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Estás enviando mensajes demasiado rápido. Espera unos segundos.",
        )

    result = await db.execute(text("""
        INSERT INTO mensaje_chat_privado (id_emisor, id_receptor, mensaje, leido, fecha)
        VALUES (:yo, :otro, :mensaje, FALSE, NOW())
        RETURNING id_mensaje, id_emisor, id_receptor, mensaje, leido, fecha
    """), {"yo": yo, "otro": otro_id, "mensaje": data.mensaje})

    mensaje = _msg_a_dict(result.fetchone())
    await db.commit()
    return mensaje
