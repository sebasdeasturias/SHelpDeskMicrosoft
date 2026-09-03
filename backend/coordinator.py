# backend/coordinator.py
# Endpoints del panel de coordinación: estadísticas, reportes, agentes,
# asignación, permisos, SLAs y búsqueda RAG. Todos leen/escriben en la BD real.
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from embeddings import generar_embedding, a_vector_sql, indexar_ticket, EMBEDDING_MODEL
from jose import jwt, JWTError
from datetime import datetime, timedelta, date
from typing import List, Optional
import json
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

    # Registro en historial con el estado ANTERIOR real (capturado antes del
    # UPDATE). Sin duplicados: el trigger automático se elimina en migración 002.
    await db.execute(text("""
        INSERT INTO historial (estado_anterior, estado_nuevo, comentario, fecha, id_solicitud, id_usuario)
        VALUES (:anterior, 'asignado', 'Ticket asignado por coordinador', NOW(), :id, :user)
    """), {"anterior": ticket[0], "id": ticket_id, "user": payload.get("user_id")})

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
    """Búsqueda semántica real: embed de la consulta (bge-m3) -> pgvector (HNSW coseno).
    Solo recupera soluciones validadas (tickets resueltos/cerrados). Retorna [] si no hay datos."""
    try:
        vec = await generar_embedding(query)
        qvec = a_vector_sql(vec)
        result = await db.execute(text("""
            SELECT s.id_solicitud, s.asunto, s.descripcion, s.estado,
                   c.nombre, COALESCE(ag.nombre, 'Sin asignar'),
                   1 - (e.embedding <=> CAST(:qvec AS vector)) AS similitud
            FROM embedding_vector e
            JOIN solicitud s ON s.id_solicitud = e.id_solicitud
            LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
            LEFT JOIN usuarios ag ON s.id_agente_asignado = ag.id_usuario
            WHERE e.modelo_embedding = :modelo
              AND s.estado IN ('resuelto', 'cerrado')
            ORDER BY e.embedding <=> CAST(:qvec AS vector)
            LIMIT 5
        """), {"qvec": qvec, "modelo": EMBEDDING_MODEL})
        filas = result.fetchall()
        resultados = [
            {
                "id_solicitud": row[0],
                "asunto": row[1],
                "descripcion": row[2],
                "estado": row[3],
                "categoria": row[4] or "General",
                "agente": row[5],
                "similitud": round(float(row[6]), 4),
            }
            for row in filas
        ]
        # Umbral calibrado para bge-m3: su piso de similitud entre textos no
        # relacionados es alto (~0.4); los matches útiles quedan por encima de 0.5
        return [r for r in resultados if r["similitud"] >= 0.50]
    except Exception as e:
        print(f"[RAG] Búsqueda vectorial no disponible: {e}")
        return []


@router.post("/rag/indexar")
async def rag_indexar(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """Indexa (backfill) todos los tickets resueltos/cerrados que aún no tengan
    embedding para el modelo actual. Exclusivo de coordinador/administrador."""
    payload = _verify_token(token)
    if payload.get("role") not in ("coordinador", "administrador"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo coordinador o administrador pueden ejecutar la indexación"
        )

    rows = await db.execute(text("""
        SELECT s.id_solicitud, s.asunto, s.descripcion
        FROM solicitud s
        WHERE s.estado IN ('resuelto', 'cerrado')
          AND NOT EXISTS (
              SELECT 1 FROM embedding_vector e
              WHERE e.id_solicitud = s.id_solicitud AND e.modelo_embedding = :modelo
          )
        ORDER BY s.fecha_actualizacion DESC
    """), {"modelo": EMBEDDING_MODEL})
    pendientes = rows.fetchall()

    indexados, errores = 0, 0
    for r in pendientes:
        try:
            if await indexar_ticket(db, r[0], r[1], r[2]):
                indexados += 1
        except Exception as e:
            errores += 1
            print(f"[RAG] Error indexando ticket {r[0]}: {e}")

    return {
        "status": "ok",
        "modelo": EMBEDDING_MODEL,
        "indexados": indexados,
        "errores": errores,
        "sin_trabajo": len(pendientes) == 0,
    }

# ============================================================
# PANEL DEL ADMINISTRADOR (rol 'administrador' exclusivo)
# ============================================================
ROLES_CANONICOS = ("solicitante", "agente", "coordinador", "administrador")
CONTENEDORES = ("helpdesk-backend", "helpdesk-db", "helpdesk-streamlit", "n8n", "ollama")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_URL = os.getenv("N8N_URL", "http://localhost:5678")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

import docker_admin
from passlib.context import CryptContext
_pwd_admin = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _require_admin(payload: dict) -> None:
    if payload.get("role") != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación es exclusiva del administrador"
        )


async def _admins_activos(db: AsyncSession) -> int:
    r = await db.execute(text(
        "SELECT count(*) FROM usuarios WHERE rol='administrador' AND estado='activo'"))
    return int(r.scalar() or 0)


@router.get("/usuarios")
async def listar_usuarios(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    r = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, area, estado, carga_trabajo,
               rol_anterior, admin_temporal_hasta, fecha_ultimo_acceso, fecha_registro
        FROM usuarios ORDER BY id_usuario
    """))
    return [
        {
            "id_usuario": x[0], "nombre": x[1], "email": x[2], "rol": x[3],
            "area": x[4], "estado": x[5], "carga_trabajo": x[6],
            "rol_anterior": x[7],
            "admin_temporal_hasta": x[8].isoformat() if x[8] else None,
            "fecha_ultimo_acceso": x[9].isoformat() if x[9] else None,
            "fecha_registro": x[10].isoformat() if x[10] else None,
        }
        for x in r.fetchall()
    ]


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
async def crear_usuario(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    nombre = (data.get("nombre") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    rol = data.get("rol") or "solicitante"
    area = (data.get("area") or "").strip() or None

    if not nombre or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre y correo son obligatorios")
    if rol not in ROLES_CANONICOS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol inválido")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña debe tener al menos 8 caracteres")
    dup = await db.execute(text("SELECT 1 FROM usuarios WHERE email = :e"), {"e": email})
    if dup.scalar():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese correo ya está registrado")

    await db.execute(text("""
        INSERT INTO usuarios (nombre, email, contraseña, rol, area, estado,
                              carga_trabajo, permisos_supervision, permisos_especiales)
        VALUES (:n, :e, :p, :r, :a, 'activo', 0, FALSE, FALSE)
    """), {"n": nombre, "e": email, "p": _pwd_admin.hash(password), "r": rol, "a": area})
    await db.commit()
    return {"status": "ok", "email": email, "rol": rol}


async def _obtener_usuario(db: AsyncSession, uid: int):
    r = await db.execute(text("""
        SELECT id_usuario, nombre, email, rol, estado FROM usuarios WHERE id_usuario = :id
    """), {"id": uid})
    return r.fetchone()


@router.patch("/usuarios/{usuario_id}")
async def actualizar_usuario(usuario_id: int, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    user = await _obtener_usuario(db, usuario_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    cambios, params = [], {"id": usuario_id}
    if "nombre" in data and (data["nombre"] or "").strip():
        cambios.append("nombre = :nombre")
        params["nombre"] = data["nombre"].strip()
    if "area" in data:
        cambios.append("area = :area")
        params["area"] = (data["area"] or "").strip() or None
    if "estado" in data and data["estado"] in ("activo", "inactivo"):
        if data["estado"] == "inactivo" and user[3] == "administrador" and user[4] == "activo":
            if await _admins_activos(db) <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Es el último administrador activo: no puede desactivarse")
        cambios.append("estado = :estado")
        params["estado"] = data["estado"]
    if data.get("password"):
        if len(data["password"]) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="La contraseña debe tener al menos 8 caracteres")
        cambios.append("contraseña = :pwd")
        params["pwd"] = _pwd_admin.hash(data["password"])

    if not cambios:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nada que actualizar")
    await db.execute(text(f"UPDATE usuarios SET {', '.join(cambios)} WHERE id_usuario = :id"), params)
    await db.commit()
    return {"status": "ok", "id_usuario": usuario_id}


@router.patch("/usuarios/{usuario_id}/rol")
async def cambiar_rol(usuario_id: int, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    user = await _obtener_usuario(db, usuario_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    nuevo_rol = data.get("rol")
    temporal_horas = data.get("temporal_horas")
    if nuevo_rol not in ROLES_CANONICOS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rol inválido")
    if usuario_id == payload.get("user_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No puedes cambiar tu propio rol (bloqueo anti-encierro)")
    if user[3] == "administrador" and nuevo_rol != "administrador":
        if await _admins_activos(db) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Es el último administrador: crea/promueve otro antes de degradarlo")

    if nuevo_rol == "administrador" and temporal_horas:
        try:
            horas = int(temporal_horas)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="temporal_horas debe ser un entero")
        if horas < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="temporal_horas debe ser >= 1")
        await db.execute(text("""
            UPDATE usuarios SET rol='administrador', rol_anterior=:anterior,
                   admin_temporal_hasta = NOW() + (:h * interval '1 hour')
            WHERE id_usuario = :id
        """), {"anterior": user[3], "h": horas, "id": usuario_id})
        resultado = {"status": "ok", "rol": "administrador", "temporal_horas": horas, "rol_anterior": user[3]}
    else:
        await db.execute(text("""
            UPDATE usuarios SET rol=:r, rol_anterior=NULL, admin_temporal_hasta=NULL WHERE id_usuario=:id
        """), {"r": nuevo_rol, "id": usuario_id})
        resultado = {"status": "ok", "rol": nuevo_rol, "temporal": False}

    await db.commit()
    return resultado


@router.delete("/usuarios/{usuario_id}")
async def eliminar_usuario(usuario_id: int, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    user = await _obtener_usuario(db, usuario_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario_id == payload.get("user_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propia cuenta")
    if user[3] == "administrador" and await _admins_activos(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Es el último administrador: no puede eliminarse")

    refs = await db.execute(text("""
        SELECT (SELECT count(*) FROM solicitud WHERE id_solicitante = :u)
             + (SELECT count(*) FROM solicitud WHERE id_agente_asignado = :u)
             + (SELECT count(*) FROM historial WHERE id_usuario = :u)
             + (SELECT count(*) FROM log_ia WHERE id_usuario = :u) AS total
    """), {"u": usuario_id})
    total = int(refs.scalar() or 0)
    if total > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El usuario tiene {total} registro(s) asociados (tickets/historial/logs): desactívalo en lugar de eliminarlo")

    await db.execute(text("DELETE FROM usuarios WHERE id_usuario = :id"), {"id": usuario_id})
    await db.commit()
    return {"status": "ok", "eliminado": usuario_id}


@router.get("/logs/{contenedor}")
async def logs_contenedor(contenedor: str, tail: int = Query(200, ge=10, le=1000),
                          db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    try:
        texto = await docker_admin.logs(contenedor, tail)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"No se pudo leer logs de '{contenedor}': {e}")
    return {"contenedor": contenedor, "logs": texto}


@router.get("/respaldos")
async def listar_respaldos(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    code, out, err = await docker_admin.exec_cmd("helpdesk-db",
        ["sh", "-c", "ls -la --time-style='+%Y-%m-%d %H:%M' /backups"])
    if code != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=err.decode("utf-8", "replace") or "No se pudo listar /backups")
    respaldos = []
    for linea in out.decode("utf-8", "replace").splitlines():
        partes = linea.split()
        if len(partes) < 8 or not partes[-1].endswith(".dump"):
            continue
        respaldos.append({"nombre": partes[-1], "bytes": int(partes[4]), "fecha": f"{partes[5]} {partes[6]}"})
    return sorted(respaldos, key=lambda r: r["nombre"], reverse=True)


@router.post("/respaldos")
async def crear_respaldo(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    nombre = f"helpdesk_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.dump"
    code, out, err = await docker_admin.exec_cmd("helpdesk-db",
        ["sh", "-c", f"pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /backups/{nombre}"], timeout=600.0)
    if code != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"pg_dump falló (exit {code}): {err.decode('utf-8', 'replace')[:300]}")
    return {"status": "ok", "archivo": nombre}


@router.get("/respaldos/{nombre}/descargar")
async def descargar_respaldo(nombre: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    if not _nombre_backup_valido(nombre):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo inválido")
    code, out, _ = await docker_admin.exec_cmd("helpdesk-db", ["sh", "-c", f"cat /backups/{nombre}"])
    if code != 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se pudo leer el respaldo")
    from fastapi import Response
    return Response(content=out, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _nombre_backup_valido(nombre: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", nombre)) and ".." not in nombre


@router.delete("/respaldos/{nombre}")
async def eliminar_respaldo(nombre: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    if not _nombre_backup_valido(nombre):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo inválido")
    code, _, err = await docker_admin.exec_cmd("helpdesk-db", ["sh", "-c", f"rm -f /backups/{nombre}"])
    if code != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo eliminar")
    return {"status": "ok", "eliminado": nombre}


@router.post("/respaldos/{nombre}/restaurar")
async def restaurar_respaldo(nombre: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    if not _nombre_backup_valido(nombre):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo inválido")
    code, out, err = await docker_admin.exec_cmd("helpdesk-db",
        ["sh", "-c", f"pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists /backups/{nombre}"],
        timeout=600.0)
    if code != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"pg_restore falló: {err.decode('utf-8', 'replace')[:300]}")
    return {"status": "ok", "restaurado": nombre}


@router.get("/bd/tablas")
async def tablas_bd(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    r = await db.execute(text("""
        SELECT relname AS tabla, n_live_tup AS filas
        FROM pg_stat_user_tables ORDER BY n_live_tup DESC, relname
    """))
    return [{"tabla": x[0], "filas": x[1]} for x in r.fetchall()]


async def _es_modelo_embeddings_ollama(modelo: str) -> tuple[bool, str]:
    """Consulta /api/tags y decide si `modelo` es de embeddings (bge-m3,
    nomic-embed, all-MiniLM...) y NO sirve para chat/generación.
    Devuelve (es_embeddings, error). error="" si la consulta fue exitosa."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            for m in resp.json().get("models", []):
                if m.get("name") == modelo:
                    fam = ((m.get("details") or {}).get("family") or "").lower()
                    nombre = (modelo or "").lower()
                    es_emb = fam == "bert" or any(
                        k in nombre for k in ("bge", "embed", "minilm", "nomic", "mxbai", "gte-"))
                    return es_emb, ""
            return False, ""
    except Exception as e:
        return False, str(e)


@router.get("/ia")
async def estado_ia(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    r = await db.execute(text("SELECT clave, valor FROM configuracion_ia"))
    config = {k: v for k, v in r.fetchall()}
    import httpx
    modelos = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            for m in resp.json().get("models", []):
                fam = ((m.get("details") or {}).get("family") or "").lower()
                nombre = (m.get("name") or "").lower()
                es_emb = fam == "bert" or any(
                    k in nombre for k in ("bge", "embed", "minilm", "nomic", "mxbai", "gte-"))
                modelos.append({
                    "name": m.get("name"),
                    "size": m.get("size", 0),
                    "tipo": "embeddings" if es_emb else "chat",
                })
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama inaccesible: {e}")
    return {"modelo_activo": config.get("modelo_chat"), "modelos": modelos, "config": config}


@router.post("/ia/modelo")
async def set_modelo_ia(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    modelo = (data.get("modelo") or "").strip()
    if not modelo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="modelo es requerido")
    # Evitar fijar como modelo de chat uno que solo sirve para embeddings.
    es_emb, err = await _es_modelo_embeddings_ollama(modelo)
    if not err and es_emb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{modelo}' es un modelo de embeddings (no genera chat). Elige un modelo como llama3.2 o qwen2.5."
        )
    await db.execute(text("""
        INSERT INTO configuracion_ia (clave, valor, descripcion)
        VALUES ('modelo_chat', :m, 'Modelo activo del chat, cambiado desde el panel del administrador')
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, fecha_actualizacion = now()
    """), {"m": modelo})
    await db.commit()
    return {"status": "ok", "modelo": modelo}


@router.post("/ia/pull")
async def pull_modelo_ia(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    modelo = (data.get("modelo") or "").strip()
    if not modelo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="modelo es requerido")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3600.0) as c:
            resp = await c.post(f"{OLLAMA_URL}/api/pull", json={"name": modelo, "stream": False})
            resp.raise_for_status()
            resultado = resp.json()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error descargando {modelo}: {e}")
    if resultado.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resultado["error"])
    return {"status": "ok", "modelo": modelo, "detalle": resultado.get("status", "descargado")}


@router.post("/ia/probar")
async def probar_modelo_ia(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    modelo = (data.get("modelo") or "").strip()
    if not modelo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="modelo es requerido")
    import httpx
    es_emb, _ = await _es_modelo_embeddings_ollama(modelo)
    try:
        async with httpx.AsyncClient(timeout=180.0) as c:
            if es_emb:
                # Los modelos de embeddings no soportan /api/generate (400).
                resp = await c.post(f"{OLLAMA_URL}/api/embed",
                    json={"model": modelo, "input": "prueba de conectividad"})
                resp.raise_for_status()
                dims = len(resp.json().get("embeddings", [[]])[0])
                return {"status": "ok", "respuesta": f"OK · embedding generado ({dims} dimensiones)"}
            resp = await c.post(f"{OLLAMA_URL}/api/generate",
                json={"model": modelo, "prompt": "Responde en una sola frase: ¿estás operativo?", "stream": False})
            resp.raise_for_status()
            return {"status": "ok", "respuesta": resp.json().get("response", "(sin respuesta)").strip()}
    except Exception as e:
        return {"status": "error", "respuesta": f"Error probando el modelo: {e}"}


@router.post("/ia/params")
async def set_params_ia(data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    permitidos = ("temperatura", "num_predict", "top_p")
    actualizados = {}
    for clave in permitidos:
        if clave in data:
            try:
                valor = str(float(data[clave])) if clave != "num_predict" else str(int(float(data[clave])))
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{clave} inválido")
            await db.execute(text("""
                INSERT INTO configuracion_ia (clave, valor, descripcion)
                VALUES (:k, :v, 'Parametro de generacion del chat')
                ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, fecha_actualizacion = now()
            """), {"k": clave, "v": valor})
            actualizados[clave] = valor
    if not actualizados:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nada que actualizar")
    await db.commit()
    return {"status": "ok", "actualizados": actualizados}


@router.get("/n8n/workflows")
async def listar_workflows(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    if not N8N_API_KEY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="N8N_API_KEY no está configurada en el .env")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{N8N_URL}/api/v1/workflows",
                            headers={"X-N8N-API-KEY": N8N_API_KEY}, params={"limit": 100})
            r.raise_for_status()
            data = r.json().get("data", [])
            return [{"id": w.get("id"), "nombre": w.get("name", "sin nombre"),
                     "activo": bool(w.get("active"))} for w in data]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error consultando n8n: {e}")


@router.post("/n8n/workflows/{workflow_id}/toggle")
async def toggle_workflow(workflow_id: str, data: dict, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = _verify_token(token)
    _require_admin(payload)
    activo = bool(data.get("activo"))
    if not N8N_API_KEY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="N8N_API_KEY no está configurada en el .env")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.patch(f"{N8N_URL}/api/v1/workflows/{workflow_id}",
                              headers={"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"},
                              content=json.dumps({"active": activo}))
            r.raise_for_status()
            return {"status": "ok", "id": workflow_id, "activo": activo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error actualizando workflow: {e}")
