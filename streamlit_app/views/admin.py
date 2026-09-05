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
import backups

N8N_URL = os.getenv("N8N_URL", "http://localhost:5678")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

palabras_peligrosas = ("insert", "update", "delete", "drop", "alter", "truncate", "grant", "create")


def render():
    es_admin = st.session_state.usuario["rol"] == "administrador"

    if es_admin:
        theme.banner(
            "Centro de Control del Administrador",
            "Potestad total: usuarios y roles, base de datos, respaldos, logs del sistema, workflows de n8n y modelos de IA.",
            badge=st.session_state.usuario['nombre'],
        )
        tab_usuarios, tab_bd, tab_backups, tab_logs, tab_n8n, tab_ia = st.tabs(
            ["Usuarios y Roles", "Base de Datos", "Respaldos", "Logs del Sistema", "N8N Workflows", "IA / Ollama"]
        )
        with tab_usuarios:
            _usuarios()
        with tab_bd:
            _consola_bd()
        with tab_backups:
            _respaldos()
        with tab_logs:
            _logs()
        with tab_n8n:
            _n8n()
        with tab_ia:
            _ia()
    else:
        # Coordinadores: solo la gestión de workflows n8n (la API key del .env
        # es compartida únicamente entre coordinadores y administradores).
        theme.banner(
            "Gestión de Workflows n8n",
            "Consulta, activa y desactiva los workflows de automatización de la plataforma.",
            badge=st.session_state.usuario['nombre'],
        )
        _n8n()


# ============================================================
# USUARIOS Y ROLES
# ============================================================
ROLES_CANONICOS = ("solicitante", "agente", "coordinador", "administrador")


def _degradar_admins_vencidos():
    """Restaura el rol de los admins temporales cuya vigencia ya expiró."""
    db.execute("""
        UPDATE usuarios
        SET rol = rol_anterior, rol_anterior = NULL, admin_temporal_hasta = NULL
        WHERE rol = 'administrador' AND rol_anterior IS NOT NULL
          AND admin_temporal_hasta IS NOT NULL AND admin_temporal_hasta < NOW()
    """)


def _admins_activos() -> int:
    return db.query(
        "SELECT count(*) AS c FROM usuarios WHERE rol='administrador' AND estado='activo'"
    )[0]["c"]


def _usuarios():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Gestión de Usuarios y Roles</h3>", unsafe_allow_html=True)
    _degradar_admins_vencidos()

    df = db.query_df("""
        SELECT id_usuario, nombre, email, rol, area, estado, carga_trabajo,
               rol_anterior, admin_temporal_hasta, fecha_ultimo_acceso
        FROM usuarios ORDER BY id_usuario
    """)
    st.dataframe(df, use_container_width=True, hide_index=True)
    admins_activos = _admins_activos()
    st.caption(f"Administradores activos: {admins_activos} · Los admins temporales vuelven a su rol anterior al vencer (se degradan en el próximo login).")

    yo = st.session_state.usuario["id_usuario"]

    # ---------- Crear usuario ----------
    with st.expander("Crear nuevo usuario"):
        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Nombre completo", key="u_nombre")
            email = st.text_input("Correo", key="u_email", placeholder="usuario@empresa.com")
            area = st.text_input("Área", key="u_area", placeholder="TI, Producción, Calidad...")
        with c2:
            rol = st.selectbox("Rol", list(ROLES_CANONICOS), key="u_rol")
            password = st.text_input("Contraseña inicial", type="password", key="u_pass",
                                     help="Mínimo 8 caracteres")
        if st.button("Crear usuario", type="primary", key="u_crear"):
            email_n = email.strip().lower()
            if not nombre or not email_n or not password:
                st.error("Nombre, correo y contraseña son obligatorios.")
            elif len(password) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif db.query("SELECT 1 FROM usuarios WHERE email = %s", (email_n,)):
                st.error("Ese correo ya está registrado.")
            else:
                from passlib.context import CryptContext
                hash_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)
                db.execute(
                    """INSERT INTO usuarios (nombre, email, contraseña, rol, area, estado,
                       carga_trabajo, permisos_supervision, permisos_especiales)
                       VALUES (%s, %s, %s, %s, %s, 'activo', 0, FALSE, FALSE)""",
                    (nombre.strip(), email_n, hash_pwd, rol, area.strip() or None),
                )
                st.success(f"Usuario '{nombre}' creado con rol {rol}.")
                time.sleep(0.4)
                st.rerun()

    # ---------- Modificar usuario ----------
    with st.expander("Modificar usuario existente"):
        opciones = {f"#{r['id_usuario']} {r['nombre']} — {r['rol']}": r["id_usuario"]
                    for _, r in df.iterrows()}
        elegido = st.selectbox("Usuario", list(opciones.keys()), key="u_elegido")
        uid = opciones[elegido]
        fila = df[df["id_usuario"] == uid].iloc[0]

        accion = st.radio(
            "Acción",
            ["Cambiar rol (permanente o temporal)", "Activar / Desactivar",
             "Restablecer contraseña", "Eliminar usuario"],
            horizontal=True, key="u_accion",
        )

        if accion == "Cambiar rol (permanente o temporal)":
            nuevo_rol = st.selectbox("Nuevo rol", list(ROLES_CANONICOS), key="u_nrol",
                                     index=list(ROLES_CANONICOS).index(fila["rol"]))
            temporal = st.checkbox("Temporal (solo para administrador)", key="u_temporal",
                                   help="El usuario vuelve automáticamente a su rol anterior al vencer.")
            horas = st.number_input("Duración (horas)", min_value=1, max_value=720, value=24,
                                    key="u_horas", disabled=not temporal)
            if st.button("Aplicar cambio de rol", key="u_aplicar_rol"):
                if uid == yo:
                    st.error("No puedes cambiar tu propio rol (bloqueo anti-encierro).")
                elif fila["rol"] == "administrador" and nuevo_rol != "administrador" and _admins_activos() <= 1:
                    st.error("Es el último administrador activo: crea/promueve otro admin antes de degradarlo.")
                else:
                    if nuevo_rol == "administrador" and temporal:
                        db.execute(
                            """UPDATE usuarios SET rol='administrador', rol_anterior=%s,
                               admin_temporal_hasta = NOW() + (%s * interval '1 hour') WHERE id_usuario=%s""",
                            (fila["rol"], int(horas), uid),
                        )
                        st.success(f"{fila['nombre']} es administrador por {int(horas)} h y volverá a '{fila['rol']}'.")
                    else:
                        db.execute(
                            """UPDATE usuarios SET rol=%s, rol_anterior=NULL,
                               admin_temporal_hasta=NULL WHERE id_usuario=%s""",
                            (nuevo_rol, uid),
                        )
                        st.success(f"Rol de {fila['nombre']} cambiado a {nuevo_rol}.")
                    time.sleep(0.4)
                    st.rerun()

        elif accion == "Activar / Desactivar":
            nuevo_estado = "inactivo" if fila["estado"] == "activo" else "activo"
            if st.button(f"Marcar como {nuevo_estado}", key="u_estado"):
                if fila["estado"] == "activo" and fila["rol"] == "administrador" and _admins_activos() <= 1:
                    st.error("Es el último administrador activo: no puede desactivarse.")
                else:
                    db.execute("UPDATE usuarios SET estado=%s WHERE id_usuario=%s", (nuevo_estado, uid))
                    st.success(f"{fila['nombre']} ahora está {nuevo_estado}.")
                    time.sleep(0.4)
                    st.rerun()

        elif accion == "Restablecer contraseña":
            nueva = st.text_input("Nueva contraseña", type="password", key="u_nueva_pass")
            if st.button("Restablecer", key="u_reset"):
                if len(nueva or "") < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                else:
                    from passlib.context import CryptContext
                    hash_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(nueva)
                    db.execute("UPDATE usuarios SET contraseña=%s WHERE id_usuario=%s", (hash_pwd, uid))
                    st.success(f"Contraseña de {fila['nombre']} restablecida.")

        elif accion == "Eliminar usuario":
            st.warning("Eliminación permanente. Si el usuario tiene tickets/asociaciones, la BD lo impedirá: desactívalo en su lugar.")
            confirmar = st.checkbox("Confirmo la eliminación definitiva", key="u_confirm_del")
            if st.button("Eliminar definitivamente", key="u_eliminar", disabled=not confirmar):
                if uid == yo:
                    st.error("No puedes eliminar tu propia cuenta.")
                elif fila["rol"] == "administrador" and _admins_activos() <= 1:
                    st.error("Es el último administrador: no puede eliminarse.")
                else:
                    try:
                        db.execute("DELETE FROM usuarios WHERE id_usuario=%s", (uid,))
                        st.success(f"{fila['nombre']} eliminado.")
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo eliminar (tiene registros asociados). Detalle: {e}")


# ============================================================
# RESPALDOS DE LA BASE DE DATOS
# ============================================================
def _respaldos():
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Respaldos de la Base de Datos</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:var(--text-dark);'>Backups <code>pg_dump -Fc</code> guardados en el volumen "
        "<code>db_backups</code> del contenedor <code>helpdesk-db</code> (/backups).</p>",
        unsafe_allow_html=True,
    )

    if st.button("Crear respaldo ahora", type="primary"):
        try:
            with st.spinner("Ejecutando pg_dump..."):
                nombre = backups.crear_respaldo()
            st.success(f"Respaldo creado: {nombre}")
        except Exception as e:
            st.error(f"Error al crear el respaldo: {e}")

    st.divider()
    try:
        respaldos = backups.listar_respaldos()
    except Exception as e:
        st.error(f"No se pudieron listar los respaldos: {e}")
        return

    if not respaldos:
        st.info("Aún no hay respaldos.")
        return

    for r in respaldos:
        c1, c2, c3, c4 = st.columns([4, 1.4, 1, 1])
        with c1:
            st.markdown(f"**{r['nombre']}**")
        with c2:
            st.caption(f"{r['bytes'] / 1e6:.2f} MB · {r['fecha']}")
        with c3:
            st.download_button("Descargar", data=backups.descargar_respaldo(r["nombre"]),
                               file_name=r["nombre"], mime="application/octet-stream",
                               key=f"dl_{r['nombre']}")
        with c4:
            if st.button("Eliminar", key=f"rm_{r['nombre']}"):
                backups.eliminar_respaldo(r["nombre"])
                st.toast(f"Respaldo {r['nombre']} eliminado")
                time.sleep(0.4)
                st.rerun()

    st.divider()
    with st.expander("Restaurar un respaldo (PELIGROSO)"):
        st.error("pg_restore --clean sobreescribe TODA la BD actual con el contenido del respaldo. "
                 "Todos los usuarios tendrán que volver a iniciar sesión y se perderán los datos creados después del backup.")
        elegido = st.selectbox("Respaldo a restaurar", [r["nombre"] for r in respaldos], key="restore_sel")
        confirmar = st.checkbox("Entiendo que la BD actual será reemplazada", key="restore_confirm")
        if st.button("Restaurar", type="primary", disabled=not confirmar):
            try:
                backups.restaurar_respaldo(elegido)
                st.success(f"Base de datos restaurada desde {elegido}.")
            except Exception as e:
                st.error(f"Error al restaurar: {e}")

    with st.expander("Automatización (recomendado)"):
        st.markdown(
            "Para respaldos automáticos programa este comando en el Programador de tareas de Windows "
            "(o cron en Linux), diario a las 03:00:\n\n"
            "```\n"
            "docker exec helpdesk-db sh -c \"pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /backups/helpdesk_auto_$(date +%Y%m%d).dump\"\n"
            "```\n\n"
            "Limpieza de respaldos con más de 30 días:\n\n"
            "```\n"
            "docker exec helpdesk-db sh -c \"find /backups -name '*.dump' -mtime +30 -delete\"\n"
            "```"
        )


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
    return ["helpdesk-backend", "helpdesk-db", "helpdesk-streamlit", "n8n", "ollama"]


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
    api_key = os.getenv("N8N_API_KEY", "").strip()
    if api_key:
        st.caption("API key cargada desde el servidor (.env) — uso restringido a coordinadores y administradores; nunca sale del backend.")
        _n8n_workflows(api_key)
    else:
        api_key = st.text_input("N8N API Key (Settings → n8n API)", value=st.session_state.get("n8n_key", ""), type="password")
        if api_key:
            st.session_state.n8n_key = api_key
            _n8n_workflows(api_key)
        else:
            st.info("Configura N8N_API_KEY en el .env (recomendado) o introduce la API Key manualmente para listar, activar y desactivar workflows.")


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
        es_emb = bool(m.get("es_embeddings"))
        with col1:
            marca = (' <span style="color:#22c55e; font-weight:700;">(activo)</span>'
                     if m["name"] == activo else "")
            etiqueta_tipo = (' <span style="color:#8b5cf6; font-size:0.72rem;">embeddings</span>' if es_emb else '')
            st.markdown(
                f"<div style='background:var(--glass-bg); border:2px solid var(--glass-border); border-radius:12px;"
                f"padding:10px 14px; color:var(--text-dark); font-weight:600;'>"
                f"{m['name']}{marca}{etiqueta_tipo} "
                f"<span style='color:var(--text-placeholder); font-size:0.78rem;'>{tam_gb:.2f} GB</span></div>",
                unsafe_allow_html=True,
            )
        with col2:
            if es_emb:
                st.caption("solo embeddings")
            elif m["name"] != activo and st.button("Usar", key=f"usar_{m['name']}", use_container_width=True):
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
                    resp = _ollama_test(m["name"], es_emb)
                st.markdown(
                    f"<div style='background:var(--glass-bg-strong); border:2px solid var(--glass-border);"
                    f"border-radius:12px; padding:12px 16px; color:var(--text-dark);'>{resp}</div>",
                    unsafe_allow_html=True,
                )

    st.divider()
    nuevo = st.text_input("Descargar un modelo nuevo (ollama pull)", placeholder="ej: llama3.2:1b, qwen2.5:3b, mistral:7b")
    if st.button("Descargar modelo", disabled=not nuevo):
        _ollama_pull(nuevo)

    st.divider()
    _parametros_ia()


def _parametros_ia():
    """Parámetros de generación del chat — se guardan en configuracion_ia y el
    backend los inyecta en el payload hacia n8n/Ollama."""
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5);'>Parámetros de la IA (chat)</h3>", unsafe_allow_html=True)
    st.caption("Se guardan en configuracion_ia y el backend los envía a n8n/Ollama en cada mensaje del chat.")

    defs = {
        "temperatura": ("Temperatura (0-2)", 0.8, "Mayor = respuestas más creativas/variadas; menor = más precisas y repetitivas."),
        "num_predict": ("Máximo de tokens generados", 512, "Límite de longitud de cada respuesta."),
        "top_p": ("Top-P (0-1)", 0.9, "Diversidad del vocabulario (nucleus sampling)."),
    }
    valores = {r["clave"]: r["valor"] for r in db.query(
        "SELECT clave, valor FROM configuracion_ia WHERE clave = ANY(%s)", (list(defs.keys()),)
    )}

    with st.form("form_params_ia"):
        c1, c2, c3 = st.columns(3)
        nuevas = {}
        with c1:
            nuevas["temperatura"] = st.number_input(
                defs["temperatura"][0], min_value=0.0, max_value=2.0, step=0.1,
                value=float(valores.get("temperatura", defs["temperatura"][1])),
                help=defs["temperatura"][2])
        with c2:
            nuevas["num_predict"] = st.number_input(
                defs["num_predict"][0], min_value=32, max_value=4096, step=32,
                value=int(float(valores.get("num_predict", defs["num_predict"][1]))),
                help=defs["num_predict"][2])
        with c3:
            nuevas["top_p"] = st.number_input(
                defs["top_p"][0], min_value=0.0, max_value=1.0, step=0.05,
                value=float(valores.get("top_p", defs["top_p"][1])),
                help=defs["top_p"][2])
        if st.form_submit_button("Guardar parámetros", type="primary"):
            for clave, valor in nuevas.items():
                db.execute(
                    """INSERT INTO configuracion_ia (clave, valor, descripcion)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, fecha_actualizacion = now()""",
                    (clave, str(valor), defs[clave][2]),
                )
            st.success("Parámetros guardados. Se aplican en el próximo mensaje del chat.")


def _modelo_activo() -> str:
    try:
        rows = db.query("SELECT valor FROM configuracion_ia WHERE clave = 'modelo_chat'")
        if rows and rows[0]["valor"]:
            return rows[0]["valor"]
    except Exception:
        pass
    return "richardyoung/qwen2.5-3b-instruct-abliterated:Q4_K_M (por defecto del backend)"


def _es_modelo_embeddings(m: dict) -> bool:
    """Heurística para distinguir modelos de embeddings (bge-m3, nomic-embed,
    all-MiniLM...) de modelos de chat/generación. Los primeros NO responden en
    /api/generate (Ollama devuelve 400), solo en /api/embed."""
    fam = ((m.get("details") or {}).get("family") or "").lower()
    if fam == "bert":
        return True
    nombre = (m.get("name") or "").lower()
    return any(k in nombre for k in ("bge", "embed", "minilm", "nomic", "mxbai", "gte-"))


def _ollama_models() -> tuple[list[dict], str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        modelos = r.json().get("models", [])
        for m in modelos:
            m["es_embeddings"] = _es_modelo_embeddings(m)
        return modelos, ""
    except Exception as e:
        return [], str(e)


def _ollama_test(modelo: str, es_embeddings: bool = False) -> str:
    try:
        if es_embeddings:
            # Los modelos de embeddings no soportan /api/generate: se prueban
            # generando un embedding real y reportando la dimensionalidad.
            r = requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": modelo, "input": "prueba de conectividad"},
                timeout=120,
            )
            r.raise_for_status()
            dims = len(r.json().get("embeddings", [[]])[0])
            return f"OK · embedding generado ({dims} dimensiones)"
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
