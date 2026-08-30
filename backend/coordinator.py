# backend/coordinator.py
# Endpoints del panel de coordinación: estadísticas, reportes, agentes,
# asignación, permisos, SLAs y búsqueda RAG. Todos leen/escriben en la BD real.
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
from datetime import datetime, timedelta, date
from typing import List, Optional
import os

router = APIRouter(prefix="/coordinator", tags=["Coordinador"])

# Roles con acceso al panel de coordinador
SUPPORT_ROLES = ("agente", "coordinador", "administrador")

# Máximo de tickets que el coordinador puede asignar a un mismo agente por día
# (control de carga de trabajo). Ajustable desde el .env.
MAX_TICKETS_AGENTE_DIA = int(os.getenv("MAX_TICKETS_AGENTE_DIA", "3"))


def _verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    if payload.get("role") not in ("coordinador", "administrador"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol coordinador")
    return payload


def _iso(dt):
    return dt.isoformat() if dt else None


# ============================================================
# ESTADÍSTICAS / KPIs
# ============================================================
@router.get("/estadisticas")
async def get_estadisticas(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)

    # --- Tickets del mes ---
    r = await db.execute(text("""
        SELECT count(*) FROM solicitud
        WHERE fecha_creacion >= date_trunc('month', now())
    """))
    total_mes = r.scalar() or 0

    # --- Cumplimiento SLA (resueltos dentro del tiempo de su prioridad) ---
    r = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE s.estado IN ('resuelto','cerrado')) AS resueltos,
            count(*) FILTER (
                WHERE s.estado IN ('resuelto','cerrado')
                  AND p.tiempo_solucion_min IS NOT NULL
                  AND EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60 <= p.tiempo_solucion_min
            ) AS resueltos_en_sla
        FROM solicitud s
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
    """))
    fila = r.fetchone()
    resueltos = fila[0] or 0
    resueltos_en_sla = fila[1] or 0
    cumplimiento_sla = (round(resueltos_en_sla / resueltos * 100, 1) if resueltos else None)

    # --- Tiempo medio de resolución (minutos) ---
    r = await db.execute(text("""
        SELECT AVG(EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60)
        FROM solicitud s
        WHERE s.estado IN ('resuelto','cerrado')
    """))
    tme = r.scalar()
    tiempo_medio = round(float(tme), 1) if tme is not None else None

    # --- Agentes / personal de soporte activo ---
    r = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE estado = 'activo') AS activos,
            count(*) AS totales
        FROM usuarios
        WHERE rol IN ('agente','coordinador','administrador')
    """))
    fila = r.fetchone()
    agentes_activos = fila[0] or 0
    agentes_totales = fila[1] or 0

    # --- Tickets sin resolver (activos) ---
    r = await db.execute(text("""
        SELECT count(*) FROM solicitud
        WHERE estado NOT IN ('cerrado')
    """))
    tickets_activos = r.scalar() or 0

    # --- Volumen por categoría (últimos 30 días) ---
    r = await db.execute(text("""
        SELECT c.nombre, count(s.id_solicitud)
        FROM categoria c
        LEFT JOIN solicitud s
            ON s.id_categoria = c.id_categoria
           AND s.fecha_creacion >= now() - interval '30 days'
        GROUP BY c.nombre
        ORDER BY count(s.id_solicitud) DESC
    """))
    categorias = [{"categoria": row[0], "total": row[1]} for row in r.fetchall()]

    # --- Eficiencia por agente ---
    r = await db.execute(text("""
        SELECT
            u.id_usuario, u.nombre, u.especialidad, u.carga_trabajo,
            count(s.id_solicitud) AS asignados,
            count(s.id_solicitud) FILTER (WHERE s.estado IN ('resuelto','cerrado')) AS resueltos,
            count(s.id_solicitud) FILTER (WHERE s.estado IN ('en_proceso','escalado')) AS en_proceso
        FROM usuarios u
        LEFT JOIN solicitud s ON s.id_agente_asignado = u.id_usuario
        WHERE u.rol IN ('agente','coordinador','administrador')
        GROUP BY u.id_usuario, u.nombre, u.especialidad, u.carga_trabajo
        ORDER BY u.nombre
    """))
    agentes_eficiencia = [
        {
            "id_usuario": row[0],
            "nombre": row[1],
            "especialidad": row[2] or "General",
            "carga_trabajo": row[3],
            "asignados": row[4],
            "resueltos": row[5],
            "en_proceso": row[6],
        }
        for row in r.fetchall()
    ]

    return {
        "kpis": {
            "total_tickets_mes": total_mes,
            "cumplimiento_sla": cumplimiento_sla,
            "tiempo_medio_solucion_min": tiempo_medio,
            "agentes_activos": agentes_activos,
            "agentes_totales": agentes_totales,
            "tickets_activos": tickets_activos,
        },
        "categorias": categorias,
        "agentes_eficiencia": agentes_eficiencia,
    }


# ============================================================
# REPORTES (filtrados en servidor)
# ============================================================
@router.get("/reportes")
async def get_reportes(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    categoria: str = Query("todas"),
    prioridad: str = Query("todas"),
    estado: str = Query("todos"),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    _verify_token(token)

    conditions = []
    params = {}

    if fecha_desde:
        try:
            params["desde"] = date.fromisoformat(fecha_desde)
            conditions.append("s.fecha_creacion >= :desde")
        except ValueError:
            pass
    if fecha_hasta:
        try:
            params["hasta"] = date.fromisoformat(fecha_hasta) + timedelta(days=1)
            conditions.append("s.fecha_creacion < :hasta")
        except ValueError:
            pass
    if categoria and categoria != "todas":
        conditions.append("c.nombre = :categoria")
        params["categoria"] = categoria
    if prioridad and prioridad != "todas":
        conditions.append("p.nivel = :prioridad")
        params["prioridad"] = prioridad
    if estado and estado != "todos":
        conditions.append("s.estado = :estado")
        params["estado"] = estado

    sql = """
        SELECT s.id_solicitud, s.asunto, c.nombre, p.nivel, s.estado,
               COALESCE(ag.nombre, 'Sin asignar'), s.fecha_creacion
        FROM solicitud s
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
        LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY s.fecha_creacion DESC"

    result = await db.execute(text(sql), params)
    tickets = [
        {
            "id_solicitud": row[0],
            "asunto": row[1],
            "categoria": row[2],
            "prioridad": row[3],
            "estado": row[4],
            "agente": row[5],
            "fecha_creacion": _iso(row[6]),
        }
        for row in result.fetchall()
    ]
    return tickets


# ============================================================
# DIRECTORIO DE AGENTES (Supervisión)
# ============================================================
@router.get("/agentes")
async def get_agentes(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)
    result = await db.execute(text("""
        SELECT id_usuario, nombre, email, tip_especialidad,
               COALESCE(nivel_jerarquia::text, 'Técnico'), permisos_supervision,
               permisos_especiales, estado, carga_trabajo, rol
        FROM (
            SELECT id_usuario, nombre, email, especialidad AS tip_especialidad,
                   nivel_jerarquia, permisos_supervision, permisos_especiales,
                   estado, carga_trabajo, rol
            FROM usuarios
            WHERE rol IN ('agente','coordinador','administrador')
        ) t
        ORDER BY nombre
    """))
    return [
        {
            "id_usuario": row[0],
            "nombre": row[1],
            "email": row[2],
            "especialidad": row[3] or "General",
            "nivel_jerarquia": row[4],
            "permisos_supervision": row[5],
            "permisos_especiales": row[6],
            "estado": row[7],
            "carga_trabajo": row[8],
            "rol": row[9],
        }
        for row in result.fetchall()
    ]


@router.post("/agentes/{usuario_id}/permisos")
async def set_permisos(usuario_id: int, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)
    await db.execute(text("""
        UPDATE usuarios
        SET permisos_supervision = COALESCE(:ps, permisos_supervision),
            permisos_especiales = COALESCE(:pe, permisos_especiales)
        WHERE id_usuario = :id
    """), {
        "ps": data.get("permisos_supervision"),
        "pe": data.get("permisos_especiales"),
        "id": usuario_id,
    })
    await db.commit()
    return {"status": "ok", "usuario_id": usuario_id}


# ============================================================
# ASIGNACIÓN DE TICKETS
# ============================================================
@router.get("/asignacion")
async def get_asignacion(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)

    # Agentes de soporte con carga y asignaciones de hoy
    result = await db.execute(text("""
        SELECT u.id_usuario, u.nombre, u.especialidad, u.carga_trabajo, u.estado,
               (SELECT count(*)
                FROM historial h
                JOIN solicitud s ON s.id_solicitud = h.id_solicitud
                WHERE s.id_agente_asignado = u.id_usuario
                  AND h.estado_nuevo = 'asignado'
                  AND h.fecha::date = CURRENT_DATE) AS asignados_hoy
        FROM usuarios u
        WHERE u.rol IN ('agente','coordinador','administrador')
        ORDER BY u.carga_trabajo ASC, u.nombre
    """))
    agentes = [
        {
            "id_usuario": row[0],
            "nombre": row[1],
            "especialidad": row[2] or "General",
            "carga_trabajo": row[3],
            "estado": row[4],
            "asignados_hoy": row[5] or 0,
        }
        for row in result.fetchall()
    ]

    # Tickets sin agente asignado
    result = await db.execute(text("""
        SELECT s.id_solicitud, s.asunto, s.estado, c.nombre, p.nivel, p.color,
               s.id_categoria
        FROM solicitud s
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
        WHERE s.id_agente_asignado IS NULL
          AND s.estado NOT IN ('cerrado')
        ORDER BY COALESCE(p.id_prioridad, 4) ASC
    """))
    sin_asignar = []
    for row in result.fetchall():
        recap = _recomendar_agente(agentes, row[4], MAX_TICKETS_AGENTE_DIA)
        sin_asignar.append({
            "id_solicitud": row[0],
            "asunto": row[1],
            "estado": row[2],
            "categoria": row[3] or "General",
            "prioridad": row[4] or "baja",
            "prioridad_color": row[5],
            "id_categoria": row[6],
            "recomendacion": recap,
        })

    return {"agentes": agentes, "sin_asignar": sin_asignar, "max_diario": MAX_TICKETS_AGENTE_DIA}


def _recomendar_agente(agentes, categoria_prioridad, max_diario=MAX_TICKETS_AGENTE_DIA):
    """Devuelve el agente con menor carga (y especialidad afín si es posible),
    priorizando a quienes aún no alcanzaron el cupo diario."""
    if not agentes:
        return None
    disponibles = [a for a in agentes if a.get("asignados_hoy", 0) < max_diario]
    candidatos = disponibles or agentes
    carga_min = min(a["carga_trabajo"] for a in candidatos)
    favoritos = [a for a in candidatos if a["carga_trabajo"] == carga_min]
    elegido = min(favoritos, key=lambda a: a["nombre"])
    # Afinidad simple: menor carga => mayor afinidad de base
    afinidad = round(95 - min(a["carga_trabajo"] for a in candidatos) * 5, 1)
    if afinidad < 60:
        afinidad = 60.0
    return {"id_usuario": elegido["id_usuario"], "nombre": elegido["nombre"], "afinidad": afinidad}


@router.post("/asignar/{ticket_id}")
async def asignar_ticket(ticket_id: int, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    agente_id = data.get("agente_id")
    if not agente_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agente_id es requerido")

    # El destino debe ser personal de soporte activo
    agente_row = await db.execute(text("""
        SELECT nombre, rol, estado FROM usuarios WHERE id_usuario = :id
    """), {"id": agente_id})
    agente = agente_row.fetchone()
    if not agente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agente no encontrado")
    if agente[1] not in SUPPORT_ROLES or agente[2] != "activo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario destino no es personal de soporte activo"
        )

    # El ticket debe existir y no estar cerrado
    ticket_row = await db.execute(text("""
        SELECT estado, id_agente_asignado FROM solicitud WHERE id_solicitud = :id
    """), {"id": ticket_id})
    ticket = ticket_row.fetchone()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")
    if ticket[0] == "cerrado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede asignar un ticket cerrado"
        )
    if ticket[1] == agente_id:
        return {"status": "ok", "ticket_id": ticket_id, "agente_id": agente_id,
                "message": "El ticket ya estaba asignado a ese agente"}

    # Límite diario de asignación por agente (control de carga de trabajo)
    hoy_row = await db.execute(text("""
        SELECT count(*)
        FROM historial h
        JOIN solicitud s ON s.id_solicitud = h.id_solicitud
        WHERE s.id_agente_asignado = :agente
          AND h.estado_nuevo = 'asignado'
          AND h.fecha::date = CURRENT_DATE
    """), {"agente": agente_id})
    asignados_hoy = hoy_row.scalar() or 0
    if asignados_hoy >= MAX_TICKETS_AGENTE_DIA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Límite diario alcanzado: {agente[0]} ya recibió {asignados_hoy} "
                    f"ticket(s) hoy (máximo {MAX_TICKETS_AGENTE_DIA}). "
                    "Elige otro agente o espera a mañana.")
        )

    result = await db.execute(text("""
        UPDATE solicitud SET id_agente_asignado = :agente, estado = 'asignado'
        WHERE id_solicitud = :id RETURNING id_solicitud
    """), {"agente": agente_id, "id": ticket_id})
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket no encontrado")

    await db.execute(text("""
        INSERT INTO historial (estado_anterior, estado_nuevo, comentario, fecha, id_solicitud, id_usuario)
        SELECT estado, 'asignado', 'Ticket asignado por coordinador', NOW(), :id, :user
        FROM solicitud WHERE id_solicitud = :id
    """), {"id": ticket_id, "user": payload.get("user_id")})

    await db.commit()
    return {
        "status": "ok", "ticket_id": ticket_id, "agente_id": agente_id,
        "asignados_hoy": asignados_hoy + 1, "max_diario": MAX_TICKETS_AGENTE_DIA,
    }


# ============================================================
# SLAs
# ============================================================
@router.get("/sla")
async def get_sla(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)
    result = await db.execute(text("""
        SELECT p.id_prioridad, p.nivel, p.color,
               p.tiempo_respuesta_min, p.tiempo_solucion_min,
               COALESCE(sl.activo, TRUE)
        FROM prioridad p
        LEFT JOIN sla sl ON sl.id_prioridad = p.id_prioridad
        ORDER BY p.id_prioridad
    """))
    return [
        {
            "id_prioridad": row[0],
            "nivel": row[1],
            "color": row[2],
            "tiempo_respuesta_min": row[3],
            "tiempo_solucion_min": row[4],
            "activo": row[5],
        }
        for row in result.fetchall()
    ]


@router.post("/sla")
async def set_sla(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)
    items = data.get("sla", [])
    for item in items:
        id_prio = item.get("id_prioridad")
        if not id_prio:
            continue
        resp = int(item.get("tiempo_respuesta_min", 0))
        sol = int(item.get("tiempo_solucion_min", 0))
        activo = item.get("activo", True)

        await db.execute(text("""
            UPDATE prioridad
            SET tiempo_respuesta_min = :resp, tiempo_solucion_min = :sol
            WHERE id_prioridad = :id
        """), {"resp": resp, "sol": sol, "id": id_prio})

        # Actualiza la fila SLA existente (upsert seguro: si no existe, la inserta)
        upd = await db.execute(text("""
            UPDATE sla
            SET tiempo_resp_max = (CAST(:resp AS text) || ' minutes')::interval,
                tiempo_sol_max = (CAST(:sol AS text) || ' minutes')::interval,
                activo = :activo
            WHERE id_prioridad = :id
            RETURNING id_sla
        """), {"resp": str(resp), "sol": str(sol), "id": id_prio, "activo": activo})
        if not upd.scalar():
            await db.execute(text("""
                INSERT INTO sla (tiempo_resp_max, tiempo_sol_max, id_prioridad, activo)
                VALUES ((CAST(:resp AS text) || ' minutes')::interval, (CAST(:sol AS text) || ' minutes')::interval, :id, :activo)
            """), {"resp": str(resp), "sol": str(sol), "id": id_prio, "activo": activo})

    await db.commit()
    return {"status": "ok", "actualizados": len(items)}


# ============================================================
# RAG (búsqueda semántica con fallback de texto)
# ============================================================
@router.get("/rag")
async def search_rag(query: str = Query(..., min_length=1), db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _verify_token(token)

    # 1) Intentar búsqueda vectorial sobre embeddings reales
    vector_rows = await _vector_search(db, query)
    if vector_rows:
        return vector_rows

    # 2) Fallback: coincidencia de texto real sobre tickets
    tokens = [t for t in query.lower().split() if len(t) > 2] or [query.lower()]
    conds = []
    params = {}
    for i, t in enumerate(tokens):
        conds.append(
            "(LOWER(s.asunto) LIKE :t{i} OR LOWER(s.descripcion) LIKE :t{i} "
            "OR LOWER(COALESCE(c.nombre,'')) LIKE :t{i})".format(i=i)
        )
        params[f"t{i}"] = f"%{t}%"
    sql = """
        SELECT s.id_solicitud, s.asunto, s.descripcion, s.estado,
               c.nombre, COALESCE(ag.nombre, 'Sin asignar')
        FROM solicitud s
        LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
        LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
        WHERE """ + " OR ".join(conds) + """
        ORDER BY s.fecha_creacion DESC
        LIMIT 5
    """
    result = await db.execute(text(sql), params)
    filas = result.fetchall()

    # Score de relevancia: tokens de la consulta presentes en el resultado
    tokens = [t for t in query.lower().split() if len(t) > 2]
    resultados = []
    for row in filas:
        texto = f"{row[1]} {row[2]} {row[5]}".lower()
        coincidencias = sum(1 for t in tokens if t in texto)
        similitud = round(coincidencias / len(tokens), 2) if tokens else 0.0
        resultados.append({
            "id_solicitud": row[0],
            "asunto": row[1],
            "descripcion": row[2],
            "estado": row[3],
            "categoria": row[4] or "General",
            "agente": row[5],
            "similitud": similitud,
        })
    return resultados


async def _vector_search(db: AsyncSession, query: str):
    """Consulta embeddings vectoriales (pgvector). Retorna [] si no hay datos."""
    try:
        # Genera un embedding simple basado en longitud como fallback seguro
        result = await db.execute(text("""
            SELECT s.id_solicitud, s.asunto, s.descripcion, s.estado,
                   c.nombre, COALESCE(ag.nombre, 'Sin asignar'),
                   1 - (e.embedding <=> (
                       SELECT embedding FROM embedding_vector ORDER BY fecha_creacion DESC LIMIT 1
                   )) AS similitud
            FROM embedding_vector e
            JOIN solicitud s ON s.id_solicitud = e.id_solicitud
            LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
            LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
            ORDER BY similitud DESC
            LIMIT 5
        """))
        filas = result.fetchall()
        if not filas:
            return []
        return [
            {
                "id_solicitud": row[0],
                "asunto": row[1],
                "descripcion": row[2],
                "estado": row[3],
                "categoria": row[4] or "General",
                "agente": row[5],
                "similitud": round(float(row[6]), 2) if row[6] is not None else 0.0,
            }
            for row in filas
        ]
    except Exception as e:
        print(f"[RAG] Vector search no disponible: {e}")
        return []
