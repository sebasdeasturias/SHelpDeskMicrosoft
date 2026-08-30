# streamlit_app/db.py
# Consultas 100% reales contra PostgreSQL (docker). Nada de datos inventados.
import os
import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

if not DATABASE_URL:
    raise ValueError("Error crítico: No se encontró DATABASE_URL. Revisa tu archivo .env")

# Compatible con la URL asyncpg del backend en ejecución local (psycopg2 no soporta el dialecto +asyncpg)
DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def query(sql: str, params=None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_df(sql: str, params=None) -> pd.DataFrame:
    return pd.DataFrame(query(sql, params))


def execute(sql: str, params=None) -> tuple[int, str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.rowcount
            status = cur.statusmessage or "OK"
        conn.commit()
    return rows, status


# ============================================================
# USUARIOS / LOGIN
# ============================================================
SQL_USUARIO_POR_EMAIL = """
    SELECT id_usuario, nombre, email, contraseña, rol, estado, especialidad,
           nivel_jerarquia, nivel_acceso
    FROM usuarios
    WHERE email = %s
"""

# ============================================================
# KPIs (mismas consultas que backend/coordinator.py /estadisticas)
# ============================================================
SQL_TOTAL_MES = """
    SELECT count(*) AS total
    FROM solicitud
    WHERE fecha_creacion >= date_trunc('month', now())
"""

SQL_TOTAL_MES_ANTERIOR = """
    SELECT count(*) AS total
    FROM solicitud
    WHERE fecha_creacion >= date_trunc('month', now()) - interval '1 month'
      AND fecha_creacion <  date_trunc('month', now())
"""

SQL_SLA = """
    SELECT
        count(*) FILTER (WHERE s.estado IN ('resuelto','cerrado')) AS resueltos,
        count(*) FILTER (
            WHERE s.estado IN ('resuelto','cerrado')
              AND p.tiempo_solucion_min IS NOT NULL
              AND EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60 <= p.tiempo_solucion_min
        ) AS resueltos_en_sla
    FROM solicitud s
    LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
"""

SQL_TIEMPO_MEDIO = """
    SELECT AVG(EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60) AS tme
    FROM solicitud s
    WHERE s.estado IN ('resuelto','cerrado')
"""

SQL_TIEMPO_MEDIO_MES = """
    SELECT AVG(EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60) AS tme
    FROM solicitud s
    WHERE s.estado IN ('resuelto','cerrado')
      AND s.fecha_actualizacion >= date_trunc('month', now())
"""

SQL_AGENTES = """
    SELECT
        count(*) FILTER (WHERE estado = 'activo') AS activos,
        count(*) AS totales
    FROM usuarios
    WHERE rol IN ('agente','coordinador','administrador')
"""

SQL_TICKETS_ACTIVOS = """
    SELECT count(*) AS total FROM solicitud WHERE estado NOT IN ('cerrado')
"""

SQL_CATEGORIAS_30D = """
    SELECT c.nombre AS categoria, count(s.id_solicitud) AS total
    FROM categoria c
    LEFT JOIN solicitud s
        ON s.id_categoria = c.id_categoria
       AND s.fecha_creacion >= now() - interval '30 days'
    GROUP BY c.nombre
    ORDER BY count(s.id_solicitud) DESC
"""

SQL_POR_ESTADO = """
    SELECT estado, count(*) AS total
    FROM solicitud
    GROUP BY estado
    ORDER BY count(*) DESC
"""

SQL_POR_PRIORIDAD = """
    SELECT p.nivel, p.color, count(s.id_solicitud) AS total
    FROM prioridad p
    LEFT JOIN solicitud s ON s.id_prioridad = p.id_prioridad
    GROUP BY p.nivel, p.color, p.id_prioridad
    ORDER BY p.id_prioridad
"""

SQL_TENDENCIA_SEMANAL = """
    SELECT to_char(date_trunc('week', fecha_creacion), 'DD/MM') AS semana,
           count(*) AS total
    FROM solicitud
    WHERE fecha_creacion >= date_trunc('week', now()) - interval '7 weeks'
    GROUP BY date_trunc('week', fecha_creacion)
    ORDER BY date_trunc('week', fecha_creacion)
"""

SQL_AGENTES_EFICIENCIA = """
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
"""

SQL_SLA_POR_PRIORIDAD = """
    SELECT
        p.nivel, p.color, p.tiempo_solucion_min,
        count(s.id_solicitud) AS total,
        count(s.id_solicitud) FILTER (WHERE s.estado IN ('resuelto','cerrado')) AS resueltos,
        count(s.id_solicitud) FILTER (
            WHERE s.estado IN ('resuelto','cerrado')
              AND p.tiempo_solucion_min IS NOT NULL
              AND EXTRACT(EPOCH FROM (s.fecha_actualizacion - s.fecha_creacion))/60 <= p.tiempo_solucion_min
        ) AS en_sla
    FROM prioridad p
    LEFT JOIN solicitud s ON s.id_prioridad = p.id_prioridad
    GROUP BY p.id_prioridad, p.nivel, p.color, p.tiempo_solucion_min
    ORDER BY p.id_prioridad
"""

SQL_IA_RESUMEN = """
    SELECT
        count(*) AS total,
        ROUND(AVG(confianza)::numeric, 3) AS confianza_prom,
        ROUND(AVG(tokens_usados)::numeric, 1) AS tokens_prom,
        ROUND(AVG(tiempo_ejecucion_ms)::numeric, 1) AS tiempo_prom_ms
    FROM clasificacion_ia
"""

SQL_IA_POR_MODELO = """
    SELECT
        COALESCE(modelo_ia, 'desconocido') AS modelo,
        count(*) AS total,
        ROUND(AVG(confianza)::numeric, 3) AS confianza_prom,
        ROUND(AVG(tokens_usados)::numeric, 1) AS tokens_prom,
        ROUND(AVG(tiempo_ejecucion_ms)::numeric, 1) AS tiempo_prom_ms
    FROM clasificacion_ia
    GROUP BY modelo_ia
    ORDER BY count(*) DESC
"""

SQL_IA_ULTIMAS = """
    SELECT ci.id_solicitud AS ticket, s.asunto, ci.categoria_ia, ci.prioridad_ia,
           ci.confianza, ci.modelo_ia, ci.tiempo_ejecucion_ms, ci.fecha_clasificacion
    FROM clasificacion_ia ci
    JOIN solicitud s ON s.id_solicitud = ci.id_solicitud
    ORDER BY ci.fecha_clasificacion DESC
    LIMIT 15
"""

SQL_TABLAS = """
    SELECT relname AS tabla, n_live_tup AS filas
    FROM pg_stat_user_tables
    ORDER BY n_live_tup DESC, relname
"""


def fetch_kpis() -> dict:
    total_mes = query(SQL_TOTAL_MES)[0]["total"]
    total_prev = query(SQL_TOTAL_MES_ANTERIOR)[0]["total"]
    sla = query(SQL_SLA)[0]
    resueltos = sla["resueltos"] or 0
    en_sla = sla["resueltos_en_sla"] or 0
    cumplimiento = round(en_sla / resueltos * 100, 1) if resueltos else None
    tme = query(SQL_TIEMPO_MEDIO)[0]["tme"]
    tme_mes = query(SQL_TIEMPO_MEDIO_MES)[0]["tme"]
    agentes = query(SQL_AGENTES)[0]
    activos_tickets = query(SQL_TICKETS_ACTIVOS)[0]["total"]

    delta_mes = None
    if total_prev:
        delta_mes = round((total_mes - total_prev) / total_prev * 100, 1)

    delta_tme = None
    if tme is not None and tme_mes is not None:
        delta_tme = round(float(tme_mes) - float(tme), 1)

    return {
        "total_mes": total_mes,
        "total_mes_anterior": total_prev,
        "delta_mes": delta_mes,
        "cumplimiento_sla": cumplimiento,
        "resueltos": resueltos,
        "en_sla": en_sla,
        "tiempo_medio": round(float(tme), 1) if tme is not None else None,
        "delta_tme": delta_tme,
        "agentes_activos": agentes["activos"] or 0,
        "agentes_totales": agentes["totales"] or 0,
        "tickets_activos": activos_tickets,
    }
