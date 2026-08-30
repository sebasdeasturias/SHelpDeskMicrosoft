# streamlit_app/app.py
# SHelpDesk — Módulo Streamlit: Coordinador (estadísticas) + Administrador (control total)
import streamlit as st
from passlib.context import CryptContext

import db
import theme
from views import estadisticas, admin

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

st.set_page_config(
    page_title="SHelpDesk Analytics",
    page_icon="assets/logohelpdesk.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.session_state.setdefault("night_mode", False)
st.session_state.setdefault("autenticado", False)
st.session_state.setdefault("usuario", None)

st.markdown(theme.get_css(), unsafe_allow_html=True)

ROLES_PERMITIDOS = ("coordinador", "administrador")


# ============================================================
# LOGIN
# ============================================================
def pantalla_login():
    col = st.columns([1, 1.2, 1])[1]
    with col:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            c_img, c_txt = st.columns([1, 2])
            with c_img:
                st.image("assets/logohelpdesk.png", use_container_width=True)
            with c_txt:
                st.markdown(
                    "<h2 style='margin:0; color:#fff; text-shadow:var(--text-glow);'>"
                    "SHelpDesk Analytics</h2>"
                    "<p style='color:var(--footer-text); font-weight:600; margin:4px 0 0 0;'>"
                    "Acceso exclusivo: Coordinador y Administrador</p>",
                    unsafe_allow_html=True,
                )
            email = st.text_input("Correo electrónico", placeholder="usuario@shelpdesk.com")
            clave = st.text_input("Contraseña", type="password", placeholder="••••••••")
            if st.button("Iniciar sesión", type="primary", use_container_width=True):
                if not email or not clave:
                    st.error("Ingresa tu correo y contraseña.")
                    return
                rows = db.query(db.SQL_USUARIO_POR_EMAIL, (email.strip().lower(),))
                if not rows:
                    st.error("Credenciales incorrectas.")
                    return
                u = rows[0]
                if u["estado"] != "activo":
                    st.error("Tu cuenta está inactiva. Contacta al administrador.")
                    return
                if not pwd_context.verify(clave, u["contraseña"]):
                    st.error("Credenciales incorrectas.")
                    return
                if u["rol"] not in ROLES_PERMITIDOS:
                    st.error(f"Acceso denegado: el rol '{u['rol']}' no usa este panel.")
                    return
                db.execute(
                    "UPDATE usuarios SET fecha_ultimo_acceso = now() WHERE id_usuario = %s",
                    (u["id_usuario"],),
                )
                u.pop("contraseña", None)
                st.session_state.autenticado = True
                st.session_state.usuario = u
                st.rerun()


# ============================================================
# APP AUTENTICADA
# ============================================================
def app_principal():
    u = st.session_state.usuario

    with st.sidebar:
        st.image("assets/logohelpdesk.png", use_container_width=True)
        st.markdown(
            f"""
<div style="background: var(--glass-bg-strong); border:2px solid var(--glass-border);
     border-radius:14px; padding:12px 14px; margin-bottom:6px;">
    <p style="margin:0; font-weight:700; font-size:0.95rem; color:var(--text-dark) !important;">{u['nombre']}</p>
    <p style="margin:2px 0 0 0; font-size:0.78rem; color:var(--text-placeholder) !important;">{u['email']}</p>
    <p style="margin:6px 0 0 0; font-size:0.75rem; color:var(--text-dark) !important;"><b>Rol:</b> {u['rol'].capitalize()}</p>
</div>""",
            unsafe_allow_html=True,
        )

        botones = st.columns(2)
        with botones[0]:
            if st.button("Noche" if not st.session_state.night_mode else "Día",
                         use_container_width=True):
                theme.toggle_night_mode()
                st.rerun()
        with botones[1]:
            if st.button("Salir", use_container_width=True):
                st.session_state.autenticado = False
                st.session_state.usuario = None
                st.rerun()

        st.divider()
        # Ambos roles acceden al centro de control; dentro, el administrador ve
        # todas las herramientas y el coordinador solo la gestión de n8n.
        opciones = ["Dashboard de Estadísticas", "Centro de Control"]
        vista = st.radio("Navegación", opciones, label_visibility="collapsed")

        st.divider()
        st.caption("Streamlit :8501 · Docker shelpdeskmicrosoft")

    if "Centro de Control" in vista:
        admin.render()
    else:
        estadisticas.render()


if st.session_state.autenticado:
    app_principal()
else:
    pantalla_login()
