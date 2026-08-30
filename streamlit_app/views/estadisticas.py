# streamlit_app/views/estadisticas.py
# Dashboard de Analítica & Estadísticas TI — datos 100% reales de la BD
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

import db
import theme


def render():
    theme.banner(
        "Dashboard de Analítica & Estadísticas TI",
        "Métricas, rendimiento de agentes y tendencias calculadas en vivo sobre la base de datos real.",
        badge="Streamlit en puerto 8501",
    )

    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        recargar = st.button("Actualizar ahora", use_container_width=True)
    with c2:
        auto = st.toggle("Auto-actualizar (30s)", value=True)
    ttl = 30 if auto else 3600

    if recargar:
        st.cache_data.clear()

    kpis = _cached_kpis(ttl)

    # ---------------- KPIs ----------------
    kc = theme.KPI_COLORS
    total, prev, delta = kpis["total_mes"], kpis["total_mes_anterior"], kpis["delta_mes"]
    trend_mes = f"{'▲' if (delta or 0) >= 0 else '▼'} {abs(delta) if delta is not None else 0}% vs mes anterior ({prev})"
    sla = kpis["cumplimiento_sla"]
    sla_txt = f"{sla}%" if sla is not None else "Sin resueltos aún"
    sla_trend = "Meta cumplida (meta >90%)" if (sla or 0) >= 90 else "Bajo la meta (meta >90%)"
    tme = kpis["tiempo_medio"]
    d_tme = kpis["delta_tme"]
    tme_trend = ""
    if d_tme is not None:
        signo, tipo = ("▼", "positive") if d_tme <= 0 else ("▲", "negative")
        tme_trend = f"{signo} {abs(d_tme)} min este mes"

    r1 = st.columns(4, gap="small")
    with r1[0]:
        st.markdown(theme.kpi_card(kc["blue"], "Tickets Totales Mes", str(total), trend_mes,
                                   "positive" if (delta or 0) >= 0 else "negative"),
                    unsafe_allow_html=True)
    with r1[1]:
        st.markdown(theme.kpi_card(kc["green"], "Cumplimiento de SLA", sla_txt, sla_trend,
                                   "positive" if (sla or 0) >= 90 else "negative"),
                    unsafe_allow_html=True)
    with r1[2]:
        st.markdown(theme.kpi_card(kc["yellow"], "Tiempo Medio Solución",
                                   f"{tme} min" if tme is not None else "—", tme_trend, "positive"),
                    unsafe_allow_html=True)
    with r1[3]:
        st.markdown(theme.kpi_card(kc["purple"], "Agentes Activos",
                                   f"{kpis['agentes_activos']} / {kpis['agentes_totales']}",
                                   f"{kpis['tickets_activos']} tickets sin cerrar"),
                    unsafe_allow_html=True)

    # ---------------- Gráficos principales ----------------
    g1, g2 = st.columns(2, gap="small")
    with g1:
        _chart_categorias(ttl)
    with g2:
        _chart_estados(ttl)

    g3, g4 = st.columns(2, gap="small")
    with g3:
        _chart_prioridad(ttl)
    with g4:
        _chart_tendencia(ttl)

    # ---------------- Agentes ----------------
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5); margin:10px 0 4px 0;'>Carga y Eficiencia de Agentes</h3>", unsafe_allow_html=True)
    a1, a2 = st.columns([3, 2], gap="small")
    with a1:
        _chart_agentes(ttl)
    with a2:
        df = _cached_agentes(ttl)
        df_v = df[["nombre", "especialidad", "carga_trabajo", "asignados", "resueltos", "en_proceso"]]
        st.dataframe(df_v, use_container_width=True, hide_index=True)

    # ---------------- SLA por prioridad ----------------
    _tabla_sla(ttl)

    # ---------------- Inteligencia Artificial ----------------
    _seccion_ia(ttl)


# ============================================================
@st.cache_data(ttl=30)
def _cached_kpis(ttl: int) -> dict:
    return db.fetch_kpis()


@st.cache_data(ttl=30)
def _cached_categorias(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_CATEGORIAS_30D)


@st.cache_data(ttl=30)
def _cached_estados(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_POR_ESTADO)


@st.cache_data(ttl=30)
def _cached_prioridad(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_POR_PRIORIDAD)


@st.cache_data(ttl=30)
def _cached_tendencia(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_TENDENCIA_SEMANAL)


@st.cache_data(ttl=30)
def _cached_agentes(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_AGENTES_EFICIENCIA)


@st.cache_data(ttl=30)
def _cached_sla(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_SLA_POR_PRIORIDAD)


@st.cache_data(ttl=30)
def _cached_ia_resumen(ttl: int) -> dict:
    r = db.query(db.SQL_IA_RESUMEN)[0]
    return {k: (float(v) if v is not None else None) for k, v in r.items()}


@st.cache_data(ttl=30)
def _cached_ia_modelos(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_IA_POR_MODELO)


@st.cache_data(ttl=30)
def _cached_ia_ultimas(ttl: int) -> pd.DataFrame:
    return db.query_df(db.SQL_IA_ULTIMAS)


# ============================================================
def _chart_categorias(ttl):
    df = _cached_categorias(ttl)
    fig = px.bar(
        df, x="categoria", y="total",
        color="total", color_continuous_scale=["#8de3df", "#3ca0d4", "#1a7495"],
        labels={"categoria": "Categoría", "total": "Tickets"},
    )
    fig.update_traces(hovertemplate="%{x}: %{y} tickets<extra></extra>")
    fig.update_layout(coloraxis_showscale=False)
    theme.plotly_layout(fig)
    _glass_chart("Volumen por Categoría", "Últimos 30 días", fig)


def _chart_estados(ttl):
    df = _cached_estados(ttl)
    colores = {
        "nuevo": "#3ca0d4", "asignado": "#8de3df", "en_proceso": "#f59e0b",
        "escalado": "#8b5cf6", "resuelto": "#10b981", "cerrado": "#11425e",
    }
    fig = px.pie(df, names="estado", values="total", hole=0.55,
                 color="estado", color_discrete_map=colores)
    fig.update_traces(textinfo="value+percent", textfont_color="#fff",
                      marker=dict(line=dict(color="rgba(255,255,255,0.6)", width=2)))
    theme.plotly_layout(fig, height=300)
    _glass_chart("Estado de Tickets", "Distribución total", fig)


def _chart_prioridad(ttl):
    df = _cached_prioridad(ttl)
    fig = px.bar(df, x="nivel", y="total", color="nivel",
                 color_discrete_map={r["nivel"]: r["color"] or "#3ca0d4" for _, r in df.iterrows()},
                 labels={"nivel": "Prioridad", "total": "Tickets"},
                 category_orders={"nivel": df["nivel"].tolist()})
    fig.update_traces(hovertemplate="%{x}: %{y} tickets<extra></extra>")
    fig.update_layout(showlegend=False)
    theme.plotly_layout(fig, height=300)
    _glass_chart("Tickets por Prioridad", "Con colores oficiales de la BD", fig)


def _chart_tendencia(ttl):
    df = _cached_tendencia(ttl)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["semana"], y=df["total"], mode="lines+markers+text",
        text=df["total"], textposition="top center",
        line=dict(color="#8de3df", width=3, shape="spline"),
        fill="tozeroy", fillcolor="rgba(141,227,223,0.25)",
        marker=dict(size=8, color="#1a7495", line=dict(color="#fff", width=1)),
        hovertemplate="Semana %{x}: %{y} tickets<extra></extra>",
    ))
    theme.plotly_layout(fig, height=300)
    _glass_chart("Tendencia de Creación", "Últimas 8 semanas", fig)


def _chart_agentes(ttl):
    df = _cached_agentes(ttl)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["nombre"], y=df["resueltos"], name="Resueltos",
                         marker_color="#10b981"))
    fig.add_trace(go.Bar(x=df["nombre"], y=df["en_proceso"], name="En proceso",
                         marker_color="#f59e0b"))
    fig.add_trace(go.Scatter(x=df["nombre"], y=df["carga_trabajo"], name="Carga de trabajo",
                             yaxis="y2", line=dict(color="#8de3df", width=2, dash="dot")))
    fig.update_layout(barmode="group", yaxis2=dict(overlaying="y", side="right", showgrid=False))
    theme.plotly_layout(fig, height=320)
    _glass_chart("Eficiencia por Agente", "Resueltos / en proceso / carga (BD real)", fig)


def _tabla_sla(ttl):
    df = _cached_sla(ttl)
    filas = []
    for _, r in df.iterrows():
        pct = (r["en_sla"] / r["resueltos"] * 100) if r["resueltos"] else None
        filas.append({
            "Prioridad": r["nivel"],
            "SLA solución": f"{r['tiempo_solucion_min']} min" if r["tiempo_solucion_min"] else "—",
            "Tickets": r["total"],
            "Resueltos": r["resueltos"],
            "Dentro de SLA": r["en_sla"],
            "Cumplimiento": f"{pct:.1f}%" if pct is not None else "—",
        })
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5); margin:10px 0 4px 0;'>Cumplimiento de SLA por Prioridad</h3>", unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)


def _seccion_ia(ttl):
    st.markdown("<h3 style='color:#fff; text-shadow:0 1px 4px rgba(0,0,0,0.5); margin:10px 0 4px 0;'>Rendimiento de la IA (clasificacion_ia)</h3>", unsafe_allow_html=True)
    r = _cached_ia_resumen(ttl)
    kc = theme.KPI_COLORS
    cols = st.columns(4, gap="small")
    with cols[0]:
        st.markdown(theme.kpi_card(kc["cyan"], "Clasificaciones IA", str(int(r["total"] or 0))),
                    unsafe_allow_html=True)
    with cols[1]:
        st.markdown(theme.kpi_card(kc["green"], "Confianza Promedio",
                                   f"{(r['confianza_prom'] or 0) * 100:.1f}%"),
                    unsafe_allow_html=True)
    with cols[2]:
        st.markdown(theme.kpi_card(kc["blue"], "Tokens Promedio",
                                   f"{r['tokens_prom'] or 0:.0f}"),
                    unsafe_allow_html=True)
    with cols[3]:
        st.markdown(theme.kpi_card(kc["yellow"], "Tiempo Promedio",
                                   f"{r['tiempo_prom_ms'] or 0:.0f} ms"),
                    unsafe_allow_html=True)

    m1, m2 = st.columns(2, gap="small")
    with m1:
        df_m = _cached_ia_modelos(ttl)
        df_m.columns = ["Modelo", "Total", "Confianza", "Tokens", "Tiempo (ms)"]
        st.markdown("**Por modelo**")
        st.dataframe(df_m, use_container_width=True, hide_index=True)
    with m2:
        df_u = _cached_ia_ultimas(ttl)
        df_u["confianza"] = (df_u["confianza"] * 100).round(1).astype(str) + "%"
        df_u = df_u[["ticket", "asunto", "categoria_ia", "prioridad_ia", "confianza", "modelo_ia"]]
        df_u.columns = ["Ticket", "Asunto", "Categoría", "Prioridad", "Confianza", "Modelo"]
        st.markdown("**Últimas clasificaciones**")
        st.dataframe(df_u, use_container_width=True, hide_index=True)


def _glass_chart(titulo: str, badge: str, fig):
    st.markdown(
        f"""
<div style="display:flex; justify-content:space-between; align-items:center; margin:2px 0 0 4px;">
    <h3 style="margin:0; color:#fff; font-size:0.95rem; text-shadow:0 1px 4px rgba(0,0,0,0.5);">{titulo}</h3>
    <span style="background:rgba(255,255,255,0.25); border:1px solid rgba(255,255,255,0.5); color:var(--text-dark);
        padding:3px 12px; border-radius:999px; font-size:0.72rem; font-weight:600;">{badge}</span>
</div>""",
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
