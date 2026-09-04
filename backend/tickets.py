from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from embeddings import indexar_ticket
from jose import jwt, JWTError
from datetime import datetime
import asyncio
import httpx
import os

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# API key que n8n debe enviar (header X-API-Key) al reportar el análisis de IA.
# Fail-closed: si no está configurada, el callback siempre se rechaza.
AI_CALLBACK_KEY = os.getenv("AI_CALLBACK_KEY")

# URL base de n8n (en docker-compose: http://n8n:5678). El backend notifica a
# n8n la creación de tickets para disparar la clasificación IA en segundo plano.
N8N_URL = os.getenv("N8N_URL", "http://n8n:5678")

# Mantener referencia a las tareas en segundo plano para evitar que el
# garbage collector las cancele prematuramente.
_tareas_n8n = set()


async def _notificar_n8n(url: str, payload: dict):
    """Fire-and-forget: avisa al workflow de n8n (nunca bloquea ni rompe la
    creación del ticket si n8n no está disponible)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            await c.post(url, json=payload)
    except Exception as e:
        print(f"[n8n] No se pudo notificar el ticket nuevo: {e}")


def _programar_notificacion(url: str, payload: dict) -> None:
    task = asyncio.create_task(_notificar_n8n(url, payload))
    _tareas_n8n.add(task)
    task.add_done_callback(_tareas_n8n.discard)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        
    if payload.get("role") != 'solicitante':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo solicitantes pueden crear tickets")
        
    asunto = data.get("asunto", "").strip()
    descripcion = data.get("descripcion", "").strip()
    id_categoria = data.get("id_categoria")
    id_prioridad = data.get("id_prioridad")
    
    if not all([asunto, descripcion, id_categoria, id_prioridad]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campos obligatorios faltantes")
        
    result = await db.execute(text("""
        INSERT INTO solicitud (asunto, descripcion, estado, id_categoria, id_prioridad, id_solicitante, fecha_creacion, fecha_actualizacion)
        VALUES (:asunto, :descripcion, 'nuevo', :id_categoria, :id_prioridad, :id_solicitante, NOW(), NOW())
        RETURNING id_solicitud
    """), {
        "asunto": asunto, 
        "descripcion": descripcion, 
        "id_categoria": id_categoria,
        "id_prioridad": id_prioridad, 
        "id_solicitante": payload.get("user_id")
    })
    ticket_id = result.scalar()
    
    await db.execute(text("""
        INSERT INTO historial (id_solicitud, estado_anterior, estado_nuevo, comentario, fecha, id_usuario)
        VALUES (:id_solicitud, NULL, 'nuevo', 'Ticket creado', NOW(), :id_usuario)
    """), {"id_solicitud": ticket_id, "id_usuario": payload.get("user_id")})
    
    await db.commit()

    # Notificación server-side al workflow de IA (n8n). Antes la hacía el
    # navegador (localhost:5678); ahora el backend avisa internamente para que
    # funcione aunque el frontend esté en otro origen (p.ej. Vercel).
    try:
        fila = (await db.execute(text("""
            SELECT c.nombre, p.nivel, u.nombre, u.email, u.area
            FROM categoria c, prioridad p, usuarios u
            WHERE c.id_categoria = :c AND p.id_prioridad = :p AND u.id_usuario = :u
        """), {"c": id_categoria, "p": id_prioridad, "u": payload.get("user_id")})).fetchone()
        if fila:
            _programar_notificacion(f"{N8N_URL}/webhook/new-ticket", {
                "event": "new_ticket_created",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "ticket_id": ticket_id,
                "ticket": {
                    "asunto": asunto,
                    "descripcion": descripcion,
                    "categoria": {"id": id_categoria, "nombre": fila[0]},
                    "prioridad": {"id": id_prioridad, "nombre": fila[1]},
                    "estado": "nuevo",
                    "fecha_creacion": datetime.utcnow().isoformat() + "Z",
                },
                "solicitante": {
                    "id": payload.get("user_id"),
                    "nombre": fila[2],
                    "email": fila[3],
                    "area": fila[4],
                },
            })
    except Exception as e:
        print(f"[n8n] No se pudo preparar la notificación del ticket {ticket_id}: {e}")

    return {"status": "created", "ticket_id": ticket_id, "message": "Ticket creado exitosamente"}


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: int, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user_role = payload.get("role")
    user_id = payload.get("user_id")
    nuevo_estado = data.get("estado")
    if not nuevo_estado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El campo 'estado' es requerido")

    if user_role not in ("agente", "coordinador", "administrador"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos para mover tickets")

    # Estado anterior: se captura ANTES del UPDATE para registrar el historial
    # con datos correctos (estado_anterior → estado_nuevo).
    anterior_row = await db.execute(
        text("SELECT estado FROM solicitud WHERE id_solicitud = :id"), {"id": ticket_id})
    estado_anterior = anterior_row.scalar()
    if estado_anterior is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    if user_role == "agente":
        # Un agente solo trabaja sobre los tickets que el coordinador le asignó
        # y nunca puede devolverlos a 'nuevo' (ese estado es del coordinador).
        if nuevo_estado == "nuevo":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Un agente no puede devolver un ticket al estado 'nuevo'"
            )
        result = await db.execute(text("""
            UPDATE solicitud SET estado = :estado, fecha_actualizacion = NOW()
            WHERE id_solicitud = :id AND id_agente_asignado = :user_id RETURNING id_solicitud
        """), {"estado": nuevo_estado, "id": ticket_id, "user_id": user_id})
        if not result.scalar():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes mover tickets que el coordinador te asignó"
            )
    else:
        # Coordinador / administrador: potestad sobre cualquier ticket
        result = await db.execute(text("""
            UPDATE solicitud SET estado = :estado, fecha_actualizacion = NOW()
            WHERE id_solicitud = :id RETURNING id_solicitud
        """), {"estado": nuevo_estado, "id": ticket_id})
        if not result.scalar():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    # El registro en historial lo hace SOLO la aplicación (con usuario y
    # estados correctos). El trigger automático de la BD que duplicaba estas
    # filas se elimina en la migración 002 (ver database/migraciones/).
    if estado_anterior != nuevo_estado:
        await db.execute(text("""
            INSERT INTO historial (estado_anterior, estado_nuevo, comentario, fecha, id_solicitud, id_usuario)
            VALUES (:anterior, :nuevo, 'Movido en tablero', NOW(), :id, :user_id)
        """), {"anterior": estado_anterior, "nuevo": nuevo_estado, "id": ticket_id, "user_id": user_id})

    await db.commit()

    # Ingesta RAG: al validar la solución, el ticket entra al índice vectorial
    if nuevo_estado in ("resuelto", "cerrado"):
        await _indexar_para_rag(db, ticket_id)

    return {"status": "ok", "ticket_id": ticket_id}


async def _indexar_para_rag(db: AsyncSession, ticket_id: int):
    """Indexa el ticket en pgvector cuando se resuelve/cierra (solución validada).
    Nunca rompe el flujo del ticket si Ollama no está disponible."""
    try:
        row = await db.execute(text("""
            SELECT asunto, descripcion FROM solicitud WHERE id_solicitud = :id
        """), {"id": ticket_id})
        t = row.fetchone()
        if t:
            await indexar_ticket(db, ticket_id, t[0], t[1])
    except Exception as e:
        print(f"[RAG] No se pudo indexar el ticket {ticket_id}: {e}")


@router.get("/{ticket_id}")
async def get_ticket_detail(ticket_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """
    Detalle completo de un ticket para el tablero Kanban:
    datos del solicitante (NUNCA la contraseña), agente asignado,
    análisis de la IA local (Ollama) e historial de estados.
    Solo disponible para roles con acceso al Kanban.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    if payload.get("role") not in ("agente", "coordinador", "administrador"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin permisos para ver el detalle del tablero"
        )

    result = await db.execute(text("""
        SELECT s.id_solicitud, s.asunto, s.descripcion, s.estado,
               s.fecha_creacion, s.fecha_actualizacion,
               c.nombre AS cat_nombre, p.nivel AS prio_nivel, p.color AS prio_color,
               sol.id_usuario, sol.nombre, sol.email, sol.area, sol.rol, sol.estado,
               sol.fecha_registro, sol.fecha_ultimo_acceso,
               ag.id_usuario, ag.nombre, ag.email, ag.especialidad, ag.carga_trabajo
        FROM solicitud s
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
        LEFT JOIN usuarios sol ON s.id_solicitante = sol.id_usuario
        LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
        WHERE s.id_solicitud = :id
    """), {"id": ticket_id})
    r = result.fetchone()

    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    ai_result = await db.execute(text("""
        SELECT prioridad_ia, categoria_ia, confianza, modelo_ia,
               tiempo_ejecucion_ms, tokens_usados, fecha_clasificacion,
               revision_manual, comentario_revision
        FROM clasificacion_ia
        WHERE id_solicitud = :id
        ORDER BY fecha_clasificacion DESC
        LIMIT 1
    """), {"id": ticket_id})
    ai = ai_result.fetchone()

    hist_result = await db.execute(text("""
        SELECT estado_anterior, estado_nuevo, comentario, fecha
        FROM historial
        WHERE id_solicitud = :id
        ORDER BY fecha DESC
        LIMIT 10
    """), {"id": ticket_id})
    historial = [
        {
            "estado_anterior": h[0],
            "estado_nuevo": h[1],
            "comentario": h[2],
            "fecha": h[3].isoformat() if h[3] else None
        }
        for h in hist_result.fetchall()
    ]

    return {
        "ticket": {
            "id_solicitud": r[0],
            "asunto": r[1],
            "descripcion": r[2],
            "estado": r[3],
            "fecha_creacion": r[4].isoformat() if r[4] else None,
            "fecha_actualizacion": r[5].isoformat() if r[5] else None,
            "categoria": r[6],
            "prioridad": r[7],
            "prioridad_color": r[8]
        },
        "solicitante": {
            "id_usuario": r[9],
            "nombre": r[10],
            "email": r[11],
            "area": r[12],
            "rol": r[13],
            "estado": r[14],
            "fecha_registro": r[15].isoformat() if r[15] else None,
            "fecha_ultimo_acceso": r[16].isoformat() if r[16] else None
        } if r[9] else None,
        "agente_asignado": {
            "id_usuario": r[17],
            "nombre": r[18],
            "email": r[19],
            "especialidad": r[20],
            "carga_trabajo": r[21]
        } if r[17] else None,
        "analisis_ia": {
            "prioridad_ia": ai[0],
            "categoria_ia": ai[1],
            "confianza": float(ai[2]) if ai[2] is not None else None,
            "modelo_ia": ai[3],
            "tiempo_ejecucion_ms": ai[4],
            "tokens_usados": ai[5],
            "fecha_clasificacion": ai[6].isoformat() if ai[6] else None,
            "revision_manual": ai[7],
            "comentario_revision": ai[8]
        } if ai else None,
        "historial": historial
    }


@router.post("/{ticket_id}/ai-analysis")
async def receive_ai_analysis(
    ticket_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(None),
):
    """Callback exclusivo de n8n (análisis IA). Protegido con API key compartida."""
    if not AI_CALLBACK_KEY or x_api_key != AI_CALLBACK_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Callback no autorizado: falta o es inválido el header X-API-Key"
        )

    id_categoria = data.get("id_categoria")
    id_prioridad = data.get("id_prioridad")
    confianza = float(data.get("confianza", 0.0))
    modelo_ia = data.get("modelo_ia", "llama3.2:3b")
    tokens_usados = int(data.get("tokens_usados", 0))
    tiempo_ejecucion_ms = int(data.get("tiempo_ejecucion_ms", 0))

    await db.execute(text("""
        UPDATE solicitud 
        SET id_categoria = :id_categoria, 
            id_prioridad = :id_prioridad, 
            fecha_actualizacion = NOW()
        WHERE id_solicitud = :ticket_id
    """), {
        "id_categoria": id_categoria,
        "id_prioridad": id_prioridad,
        "ticket_id": ticket_id
    })
    
    cat_result = await db.execute(text("SELECT nombre FROM categoria WHERE id_categoria = :id"), {"id": id_categoria})
    cat_nombre = cat_result.scalar() or "Desconocida"
    
    prio_result = await db.execute(text("SELECT nivel FROM prioridad WHERE id_prioridad = :id"), {"id": id_prioridad})
    prio_nombre = prio_result.scalar() or "Desconocida"
    
    await db.execute(text("""
        INSERT INTO clasificacion_ia (
            id_solicitud, prioridad_ia, categoria_ia, confianza, 
            modelo_ia, tiempo_ejecucion_ms, tokens_usados, fecha_clasificacion
        ) VALUES (
            :ticket_id, :prio_nombre, :cat_nombre, :confianza, 
            :modelo_ia, :tiempo_ms, :tokens, NOW()
        )
    """), {
        "ticket_id": ticket_id,
        "prio_nombre": prio_nombre,
        "cat_nombre": cat_nombre,
        "confianza": confianza,
        "modelo_ia": modelo_ia,
        "tiempo_ms": tiempo_ejecucion_ms,
        "tokens": tokens_usados
    })
    
    await db.commit()
    
    return {
        "status": "success", 
        "message": "Análisis de IA almacenado correctamente",
        "ticket_id": ticket_id
    }

@router.get("")
async def get_tickets(
    since: str = Query(None),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)  # ← FIX BUG #2: requerir autenticación
):
    # Validar token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    
    user_role = payload.get("role")
    user_id = payload.get("user_id")

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        except ValueError:
            since_dt = None

    base_query = """
        SELECT s.id_solicitud, s.id_solicitante, s.asunto, s.descripcion, s.estado, s.prioridad, s.categoria,
        s.fecha_creacion, s.fecha_actualizacion, s.id_agente_asignado,
        u.nombre as agente_nombre,
        c.nombre as cat_nombre,
        p.nivel as prio_nivel, p.color as prio_color,
        ci.confianza, ci.prioridad_ia
        FROM solicitud s
        LEFT JOIN usuarios u ON s.id_agente_asignado = u.id_usuario
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
        LEFT JOIN clasificacion_ia ci ON s.id_solicitud = ci.id_solicitud AND ci.revision_manual = FALSE
    """
    
    # FIX BUG #3: filtrar por solicitante en el servidor
    params = {}
    conditions = []
    if user_role == 'solicitante':
        conditions.append("s.id_solicitante = :user_id")
        params["user_id"] = user_id
    elif user_role == 'agente':
        # Un agente SOLO ve los tickets que el coordinador le asignó.
        # Los tickets 'nuevo' (sin asignar) son exclusivos del kanban del coordinador,
        # que es quien los reparte desde la pantalla de Asignación.
        conditions.append("s.id_agente_asignado = :user_id")
        conditions.append("s.estado != 'nuevo'")
        params["user_id"] = user_id
    # coordinador / administrador: ven todos los tickets (incluidos los 'nuevo')
    if since_dt:
        conditions.append("(s.fecha_actualizacion >= :since OR s.fecha_creacion >= :since)")
        params["since"] = since_dt
    
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY s.fecha_creacion DESC"
    
    result = await db.execute(text(base_query), params)
    rows = result.fetchall()
    
    tickets = []
    for r in rows:
        tickets.append({
            "id_solicitud": r[0],
            "id_solicitante": r[1],
            "asunto": r[2],
            "descripcion": r[3],
            "estado": r[4],
            "prioridad": r[5],
            "categoria": r[6],
            "fecha_creacion": r[7].isoformat() if r[7] else None,
            "fecha_actualizacion": r[8].isoformat() if r[8] else None,
            "id_agente_asignado": r[9],
            "agente": r[10] or "Sin asignar",
            "cat_nombre": r[11],
            "prio_nivel": r[12],
            "prio_color": r[13],
            "confianza_ia": float(r[14]) if r[14] else None,
            "prioridad_ia": r[15]
        })
    return tickets