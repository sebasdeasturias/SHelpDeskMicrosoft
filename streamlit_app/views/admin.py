# streamlit_app/views/admin.py
# Herramientas exclusivas del administrador: BD, logs, n8n e IA
import json
import os
import time
import requests
import streamlit as st
import pandas as pd

import db
import theme
import docker_api

N8N_URL = os.getenv("N8N_URL", "http://localhost:5678")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

palabras_peligrosas = ("insert", "update", "delete", "drop", "alter", "truncate", "grant", "create")


def render():
    theme.banner(
        "Centro de Control del Administrador",
        "Potestad total: base de datos, logs del sistema, workflows de n8n y modelos de IA.",
        badge=st.session_state.usuario['nombre'],
    )

    tab_bd, tab_logs, tab_n8n, tab_ia = st.tabs(
        ["Base de Datos", "Logs del Sistema", "N8N Workflows", "IA / Ollama"]
    )
    with tab_bd:
        _consola_bd()
    with tab_logs:
        _logs()
    with tab_n8n:
        _n8n()
    with tab_ia:
        _ia()


# ============================================================
# CONSOLA SQL
# ============================================================
def _consola_bd():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Consola SQL directa</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:var(--text-dark);'>"
        "Ejecuta SQL real contra <code>helpdesk_db</code> (PostgreSQL en docker).</p>",
        unsafe_allow_html=True,
    )

    modo = st.radio(
        "Modo de ejecución",
        ["Solo lectura (SELECT/EXPLAIN)", "Escritura permitida (INSERT/UPDATE/DELETE/DDL)"],
        horizontal=True,
    )
    sql = st.text_area(
        "Sentencia SQL",
        value="SELECT estado, count(*) AS total FROM solicitud GROUP BY estado ORDER BY total DESC;",
        height=140,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        ejecutar = st.button("Ejecutar", type="primary", use_container_width=True)
    with c2:
        ver_tablas = st.button("Ver tablas y filas", use_container_width=True)

    if ver_tablas:
        df = db.query_df(db.SQL_TABLAS)
        st.dataframe(df, use_container_width=True, hide_index=True)

    if not ejecutar:
        return

    es_escritura = any(w in sql.lower() for w in palabras_peligrosas)
    if es_escritura and "Solo lectura" in modo:
        st.error("Bloqueado: el modo 'Solo lectura' no permite sentencias de escritura. Cambia de modo si eres el administrador.")
        return
    if es_escritura and "Escritura" in modo:
        st.warning(f"Vas a ejecutar una sentencia de ESCRITURA:\n\n```sql\n{sql.strip()}\n```")
        if not st.checkbox("Confirmo la ejecución de escritura"):
            st.info("Operación cancelada.")
            return

    try:
        t0 = time.perf_counter()
        if es_escritura:
            rows, status = db.execute(sql)
            ms = (time.perf_counter() - t0) * 1000
            st.success(f"{status} — filas afectadas: {rows} ({ms:.0f} ms)")
        else:
            df = db.query_df(sql)
            ms = (time.perf_counter() - t0) * 1000
            st.caption(f"{len(df)} filas · {ms:.0f} ms")
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error de PostgreSQL: {e}")


# ============================================================
# LOGS
# ============================================================
def _logs():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Logs en vivo de los contenedores</h3>", unsafe_allow_html=True)
    disponibles = [c["nombre"] for c in docker_api.list_containers()]
    if not disponibles:
        st.error("No se pudo acceder al motor de Docker (socket no montado ni CLI local disponible).")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        conts = st.multiselect("Contenedores", disponibles,
                               default=[d for d in _log_defaults() if d in disponibles])
    with c2:
        tail = st.selectbox("Líneas", [50, 100, 200, 500], index=2)

    if st.button("Refrescar logs", use_container_width=False):
        st.cache_data.clear()
        st.rerun()

    for nombre in conts:
        with st.expander(f"Contenedor: {nombre}", expanded=(len(conts) <= 2)):
            logs = docker_api.container_logs(nombre, tail)
            st.code(logs if logs else "(sin logs)", language="log")


def _log_defaults():
    return ["helpdesk-backend", "helpdesk-db"]


# ============================================================
# N8N
# ============================================================
def _n8n():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Gestión de n8n</h3>", unsafe_allow_html=True)

    ok, detalle = _n8n_health()
    if ok:
        st.success(f"n8n accesible en {N8N_URL} ({detalle})")
    else:
        st.error(f"n8n NO accesible en {N8N_URL}: {detalle}")

    st.link_button("Abrir editor n8n (puerto 5678)", "http://localhost:5678", use_container_width=True)

    st.divider()
    api_key = st.text_input("N8N API Key (Settings → n8n API)", value=st.session_state.get("n8n_key", ""), type="password")
    if api_key:
        st.session_state.n8n_key = api_key
        _n8n_workflows(api_key)
    else:
        st.info("Introduce la API Key para listar, activar y desactivar workflows desde aquí (potestad total del administrador).")


def _n8n_health() -> tuple[bool, str]:
    try:
        r = requests.get(f"{N8N_URL}/healthz", timeout=5)
        return r.status_code == 200, f"healthz {r.status_code}"
    except Exception as e:
        return False, str(e)


def _n8n_workflows(api_key: str):
    headers = {"X-N8N-API-KEY": api_key}
    try:
        r = requests.get(f"{N8N_URL}/api/v1/workflows", headers=headers, timeout=10, params={"limit": 100})
        if r.status_code != 200:
            st.error(f"La API de n8n respondió {r.status_code}: {r.text[:300]}")
            return
        data = r.json().get("data", [])
        if not data:
            st.info("No hay workflows en esta instancia de n8n.")
            return
        for wf in data:
            punto = ('<span style="display:inline-block; width:10px; height:10px; border-radius:50%;'
                     'background:#22c55e; margin-right:8px;"></span>' if wf.get("active")
                     else '<span style="display:inline-block; width:10px; height:10px; border-radius:50%;'
                          'background:#9ca3af; margin-right:8px;"></span>')
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"<div style='background:var(--glass-bg); border:2px solid var(--glass-border);"
                    f"border-radius:12px; padding:10px 14px;'>"
                    f"<b style='color:var(--text-dark);'>{punto}{wf.get('name', 'sin nombre')}</b> "
                    f"<span style='color:var(--text-placeholder); font-size:0.78rem;'>"
                    f"ID: {wf.get('id')} · {'Activo' if wf.get('active') else 'Inactivo'}</span></div>",
                    unsafe_allow_html=True,
                )
            with col2:
                accion = "Desactivar" if wf.get("active") else "Activar"
                if st.button(accion, key=f"wf_{wf.get('id')}", use_container_width=True):
                    nuevo = not bool(wf.get("active"))
                    resp = requests.patch(
                        f"{N8N_URL}/api/v1/workflows/{wf.get('id')}",
                        headers={**headers, "Content-Type": "application/json"},
                        data=json.dumps({"active": nuevo}), timeout=10,
                    )
                    if resp.status_code == 200:
                        st.toast(f"Workflow '{wf.get('name')}' {'activado' if nuevo else 'desactivado'}")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error(f"Error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        st.error(f"No se pudo consultar la API de n8n: {e}")


# ============================================================
# IA / OLLAMA
# ============================================================
def _ia():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Consola de IA (Ollama)</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:var(--text-dark);'>"
        "El modelo activo se guarda en la tabla <code>configuracion_ia</code> (clave <code>modelo_chat</code>) "
        "y el backend lo usa como modelo por defecto para el chat.</p>",
        unsafe_allow_html=True,
    )

    activo = _modelo_activo()
    st.markdown(
        f"<div style='background:var(--glass-bg-strong); border:2px solid var(--glass-border); border-radius:14px;"
        f"padding:14px 18px; margin-bottom:10px;'>"
        f"<span style='color:var(--text-dark); font-weight:600;'>"
        f"Modelo activo del chat: <b>{activo}</b></span></div>",
        unsafe_allow_html=True,
    )

    modelos, err = _ollama_models()
    if err:
        st.error(f"No se pudo conectar con Ollama ({OLLAMA_URL}): {err}")
        return
    if not modelos:
        st.warning("Ollama no tiene modelos descargados todavía.")
        return

    st.markdown("**Modelos instalados**")
    for m in modelos:
        col1, col2, col3 = st.columns([3, 1, 1])
        tam_gb = m.get("size", 0) / 1e9
        with col1:
            marca = (' <span style="color:#22c55e; font-weight:700;">(activo)</span>'
                     if m["name"] == activo else "")
            st.markdown(
                f"<div style='background:var(--glass-bg); border:2px solid var(--glass-border); border-radius:12px;"
                f"padding:10px 14px; color:var(--text-dark); font-weight:600;'>"
                f"{m['name']}{marca} "
                f"<span style='color:var(--text-placeholder); font-size:0.78rem;'>{tam_gb:.2f} GB</span></div>",
                unsafe_allow_html=True,
            )
        with col2:
            if m["name"] != activo and st.button("Usar", key=f"usar_{m['name']}", use_container_width=True):
                db.execute(
                    """
                    INSERT INTO configuracion_ia (clave, valor, descripcion)
                    VALUES ('modelo_chat', %s, 'Modelo activo del chat, cambiado desde el panel del administrador')
                    ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, fecha_actualizacion = now()
                    """,
                    (m["name"],),
                )
                st.toast(f"Modelo activo cambiado a {m['name']}")
                time.sleep(0.4)
                st.rerun()
        with col3:
            if st.button("Probar", key=f"test_{m['name']}", use_container_width=True):
                with st.spinner(f"Consultando a {m['name']}..."):
                    resp = _ollama_test(m["name"])
                st.markdown(
                    f"<div style='background:var(--glass-bg-strong); border:2px solid var(--glass-border);"
                    f"border-radius:12px; padding:12px 16px; color:var(--text-dark);'>{resp}</div>",
                    unsafe_allow_html=True,
                )

    st.divider()
    nuevo = st.text_input("Descargar un modelo nuevo (ollama pull)", placeholder="ej: llama3.2:1b, qwen2.5:3b, mistral:7b")
    if st.button("Descargar modelo", disabled=not nuevo):
        _ollama_pull(nuevo)


def _modelo_activo() -> str:
    try:
        rows = db.query("SELECT valor FROM configuracion_ia WHERE clave = 'modelo_chat'")
        if rows and rows[0]["valor"]:
            return rows[0]["valor"]
    except Exception:
        pass
    return "llama3.2:3b (por defecto del backend)"


def _ollama_models() -> tuple[list[dict], str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return r.json().get("models", []), ""
    except Exception as e:
        return [], str(e)


def _ollama_test(modelo: str) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "prompt": "Responde en una sola frase: ¿estás operativo?", "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("response", "(sin respuesta)").strip()
    except Exception as e:
        return f"Error probando el modelo: {e}"


def _ollama_pull(modelo: str):
    placeholder = st.empty()
    barra = st.progress(0.0, text=f"Descargando {modelo}...")
    try:
        with requests.post(f"{OLLAMA_URL}/api/pull", json={"name": modelo}, stream=True, timeout=3600) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    barra.empty()
                    st.error(f"Error en la descarga: {data['error']}")
                    return
                total = data.get("total") or 0
                done = data.get("completed") or 0
                if total and done:
                    barra.progress(done / total, text=f"Descargando {modelo}: {done/1e9:.2f}/{total/1e9:.2f} GB")
                if data.get("status") == "success":
                    barra.progress(1.0, text=f"Modelo {modelo} descargado")
                    st.success(f"Modelo {modelo} instalado.")
    except Exception as e:
        barra.empty()
        st.error(f"Error descargando {modelo}: {e}")
