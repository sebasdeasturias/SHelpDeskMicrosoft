# streamlit_app/theme.py
# Estética Glassmorphism Frutiger Aero (réplica de frontend/styles)
import streamlit as st

DAY = {
    "glass-bg": "rgba(255, 255, 255, 0.25)",
    "glass-border": "rgba(255, 255, 255, 0.5)",
    "glass-bg-strong": "rgba(255, 255, 255, 0.45)",
    "btn-top": "#8de3df",
    "btn-bottom": "#1a7495",
    "sky-top": "#10599d",
    "sky-mid": "#3ca0d4",
    "sky-low": "#87ceeb",
    "grass": "#429d29",
    "grid-color": "rgba(255,255,255,0.15)",
    "text-dark": "#11425e",
    "text-placeholder": "#3b7491",
    "icon-color": "#4a8cae",
    "footer-text": "#0b3147",
    "link-color": "#004d6b",
    "link-hover": "#0076a3",
    "text-glow": "0 2px 4px rgba(0,0,0,0.4), 0 0 10px rgba(255,255,255,0.6)",
    "stars-opacity": "0.0",
}

NIGHT = {
    "glass-bg": "rgba(30,30,50,0.45)",
    "glass-border": "rgba(100,100,150,0.35)",
    "glass-bg-strong": "rgba(40,40,70,0.65)",
    "btn-top": "#4a6fa5",
    "btn-bottom": "#1a2a4a",
    "sky-top": "#000000",
    "sky-mid": "#0a0a2e",
    "sky-low": "#1a1a3e",
    "grass": "#0d2818",
    "grid-color": "rgba(100,100,200,0.1)",
    "text-dark": "#e0e0ff",
    "text-placeholder": "#8888aa",
    "icon-color": "#a0a0d0",
    "footer-text": "#c0c0e0",
    "link-color": "#88aaff",
    "link-hover": "#aaccff",
    "text-glow": "0 2px 4px rgba(0,0,0,0.8), 0 0 10px rgba(200,200,255,0.3)",
    "stars-opacity": "0.8",
}

CHART_FONT = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"


def toggle_night_mode():
    """Toggle día/noche guardado en session_state."""
    st.session_state.night_mode = not st.session_state.get("night_mode", False)


def plotly_layout(fig, height=320):
    """Layout base para que los gráficos floten sobre el cristal."""
    night = st.session_state.get("night_mode", False)
    txt = "#e0e0ff" if night else "#11425e"
    grid = "rgba(100,100,200,0.25)" if night else "rgba(255,255,255,0.45)"
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=CHART_FONT, color=txt, size=13),
        title_font=dict(family=CHART_FONT, color=txt, size=15),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=grid, zerolinecolor=grid),
        yaxis=dict(gridcolor=grid, zerolinecolor=grid),
    )
    return fig


def get_css() -> str:
    v = NIGHT if st.session_state.get("night_mode", False) else DAY
    return f"""
<style>
:root {{
    --glass-bg: {v['glass-bg']};
    --glass-border: {v['glass-border']};
    --glass-bg-strong: {v['glass-bg-strong']};
    --btn-top: {v['btn-top']};
    --btn-bottom: {v['btn-bottom']};
    --sky-top: {v['sky-top']};
    --sky-mid: {v['sky-mid']};
    --sky-low: {v['sky-low']};
    --grass: {v['grass']};
    --grid-color: {v['grid-color']};
    --text-dark: {v['text-dark']};
    --text-placeholder: {v['text-placeholder']};
    --icon-color: {v['icon-color']};
    --footer-text: {v['footer-text']};
    --link-color: {v['link-color']};
    --link-hover: {v['link-hover']};
    --text-glow: {v['text-glow']};
    --priority-critical: #ff4444;
    --priority-high: #ff8800;
    --priority-medium: #ffcc00;
    --priority-low: #44bb44;
}}

/* Fondo frutiger aero fijo (cielo + rejilla + estrellas) */
#aero-bg, #aero-grid, #aero-stars {{
    position: fixed; width: 100vw; height: 100vh; top: 0; left: 0; z-index: 0;
    pointer-events: none;
}}
#aero-bg {{
    background: linear-gradient(to bottom,
        var(--sky-top) 0%, var(--sky-mid) 50%, var(--sky-low) 75%, var(--grass) 100%);
    z-index: -3; transition: background 0.5s ease;
}}
#aero-grid {{
    background-image:
        linear-gradient(var(--grid-color) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
    background-size: 40px 40px; z-index: -2;
}}
#aero-stars {{
    background-image:
        radial-gradient(2px 2px at 20px 30px, #fff, transparent),
        radial-gradient(2px 2px at 40px 70px, #fff, transparent),
        radial-gradient(1px 1px at 90px 40px, #fff, transparent),
        radial-gradient(1px 1px at 130px 80px, #fff, transparent),
        radial-gradient(2px 2px at 160px 30px, #fff, transparent),
        radial-gradient(1px 1px at 200px 60px, #fff, transparent),
        radial-gradient(2px 2px at 250px 20px, #fff, transparent),
        radial-gradient(1px 1px at 300px 90px, #fff, transparent);
    background-size: 350px 120px; background-repeat: repeat;
    z-index: -1; opacity: {v['stars-opacity']}; transition: opacity 0.5s ease;
}}

/* App transparente para ver el cielo */
.stApp {{
    background: transparent;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stAppViewContainer"] {{ background: transparent; }}
[data-testid="stMain"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 1.4rem; max-width: 1400px; }}
#MainMenu {{ visibility: visible; }}
footer {{ visibility: hidden; }}

/* Sidebar de cristal */
[data-testid="stSidebar"] {{
    background: var(--glass-bg);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-right: 2px solid var(--glass-border);
    box-shadow: 8px 0 32px rgba(0,0,0,0.2);
}}
[data-testid="stSidebar"] * {{
    color: var(--text-dark) !important;
}}
[data-testid="stSidebar"] hr {{ border-color: var(--glass-border); }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
    color: var(--footer-text) !important; opacity: 0.9;
}}

/* Enlaces con la paleta del login */
.stApp a {{ color: var(--link-color); }}
.stApp a:hover {{ color: var(--link-hover); }}

/* Tarjetas de cristal (st.container(border=True)) */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--glass-bg);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 2px solid var(--glass-border) !important;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}}

/* Botones con gradiente frutiger */
.stButton > button {{
    background: linear-gradient(to bottom, var(--btn-top), var(--btn-bottom));
    color: white;
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: 12px;
    font-weight: 600;
    text-shadow: var(--text-glow);
    box-shadow: 0 4px 10px rgba(0,0,0,0.25), inset 0 2px 5px rgba(255,255,255,0.5);
    transition: transform 0.2s;
}}
.stButton > button:hover {{
    transform: translateY(-2px);
    color: white; border: 1px solid rgba(255,255,255,0.7);
    background: linear-gradient(to bottom, var(--btn-top), var(--btn-bottom));
}}
.stButton > button:focus:not(:active) {{
    color: white;
    border-color: rgba(255,255,255,0.6);
    box-shadow: 0 4px 10px rgba(0,0,0,0.25), inset 0 2px 5px rgba(255,255,255,0.5);
}}

/* Inputs de cristal */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div,
.stNumberInput > div > div > input {{
    background: var(--glass-bg-strong) !important;
    color: var(--text-dark) !important;
    border: 2px solid var(--glass-border) !important;
    border-radius: 10px;
    backdrop-filter: blur(6px);
}}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {{
    color: var(--text-placeholder) !important;
}}
.stSelectbox > div > div {{ color: var(--text-dark) !important; }}
.stSelectbox [data-baseweb="popover"] > div {{
    background: rgba(255,255,255,0.92);
}}
.stNumberInput input {{ color: var(--text-dark) !important; }}

/* Toggles / radios / sliders */
[data-testid="stCheckbox"] span, [data-testid="stRadio"] label, [data-testid="stToggle"] p {{
    color: var(--text-dark) !important;
}}
[data-baseweb="checkbox"] div[aria-checked] {{
    background: var(--btn-bottom) !important; border-color: var(--glass-border) !important;
}}
.stRadio div[role="radiogroup"] label span {{ color: var(--text-dark) !important; }}

/* Tabs de cristal */
.stTabs [data-baseweb="tab-list"] {{
    gap: 6px;
    background: var(--glass-bg);
    border: 2px solid var(--glass-border);
    border-radius: 14px;
    padding: 6px;
    backdrop-filter: blur(10px);
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 10px;
    color: var(--text-dark);
    font-weight: 600;
}}
.stTabs [aria-selected="true"] {{
    background: linear-gradient(to bottom, var(--btn-top), var(--btn-bottom));
    color: white !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: transparent; }}
.stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* DataFrames y tablas de cristal */
[data-testid="stDataFrame"] {{
    border-radius: 12px; overflow: hidden;
}}
[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {{
    background: var(--glass-bg-strong);
}}
[data-testid="stTable"], .stDataFrame [role="table"] {{ color: var(--text-dark); }}

/* Métricas nativas adaptadas */
[data-testid="stMetric"] {{
    background: var(--glass-bg-strong);
    border: 2px solid var(--glass-border);
    border-radius: 14px; padding: 14px 16px;
    backdrop-filter: blur(8px);
}}
[data-testid="stMetricLabel"] p {{ color: var(--text-placeholder) !important; }}
[data-testid="stMetricValue"] {{ color: var(--text-dark) !important; }}
[data-testid="stMetricDelta"] svg {{ display: none; }}

/* Alertas de cristal */
[data-testid="stAlert"] {{
    background: var(--glass-bg-strong);
    backdrop-filter: blur(8px);
    border: 2px solid var(--glass-border);
    border-radius: 12px;
    color: var(--text-dark) !important;
}}
[data-testid="stAlert"] p {{ color: var(--text-dark) !important; }}

/* Código y expanders */
.stCode > div, pre {{
    background: rgba(10, 25, 40, 0.75) !important;
    border-radius: 12px;
    border: 1px solid var(--glass-border);
    color: #d8f3ff !important;
}}
[data-testid="stExpander"] {{
    background: var(--glass-bg);
    border: 2px solid var(--glass-border);
    border-radius: 14px;
    backdrop-filter: blur(8px);
}}
[data-testid="stExpander"] summary {{ color: var(--text-dark) !important; }}

/* Barras de progreso */
[data-testid="stProgress"] > div {{ background: linear-gradient(to right, var(--btn-top), var(--btn-bottom)); }}

/* Scrollbar */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
    background: var(--glass-bg-strong);
    border-radius: 8px; border: 1px solid var(--glass-border);
}}
</style>
<div id="aero-bg"></div><div id="aero-grid"></div><div id="aero-stars"></div>
"""


def banner(title: str, subtitle: str, badge: str = "") -> None:
    """Cabecera tipo panel-header-banner del coordinador."""
    html = f"""
<div class="panel-banner" style="
    display:flex; justify-content:space-between; align-items:center; gap:14px; flex-wrap:wrap;
    background: var(--glass-bg);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border: 2px solid var(--glass-border); border-radius: 16px;
    padding: 18px 22px; box-shadow: 0 8px 32px rgba(0,0,0,0.2); margin-bottom: 6px;">
    <div>
        <h2 style="margin:0; color:#fff; text-shadow:var(--text-glow);
            font-size:1.35rem;">{title}</h2>
        <p style="margin:6px 0 0 0; color:var(--text-dark); opacity:0.92; font-size:0.92rem;">
            {subtitle}</p>
    </div>"""
    if badge:
        html += f"""
    <span style="background:rgba(255,255,255,0.3); border:1px solid var(--glass-border); color:var(--text-dark); padding:6px 14px; border-radius:999px; font-size:0.78rem; font-weight:600;">{badge}</span>"""
    html += """
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def kpi_card(color: str, label: str, value: str, trend: str = "", trend_type: str = "neutral") -> str:
    """Tarjeta KPI idéntica a .kpi-card del dashboard-coordinador.css."""
    color_map = {
        "positive": "#22c55e",
        "negative": "#ff6b6b",
        "neutral": "var(--text-placeholder)",
    }
    trend_color = color_map.get(trend_type, color_map["neutral"])

    html = f"""
<div class="kpi-card" style="
    display:flex; align-items:center; gap:14px;
    background: var(--glass-bg);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border: 2px solid var(--glass-border); border-radius: 16px;
    padding: 16px 18px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);">
    <div style="width:48px; height:48px; border-radius:12px; flex-shrink:0;
        background: {color}; box-shadow: 0 4px 12px rgba(0,0,0,0.25);"></div>
    <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
        <span style="font-size:0.72rem; color:var(--text-placeholder); font-weight:600;
            text-transform:uppercase; letter-spacing:0.4px;">{label}</span>
        <span style="font-size:1.5rem; font-weight:700; color:var(--text-dark); line-height:1.1;">{value}</span>"""
    if trend:
        html += f"""
        <span style="font-size:0.7rem; font-weight:600; color:{trend_color};">{trend}</span>"""
    html += """
    </div>
</div>
"""
    return html


KPI_COLORS = {
    "blue": "linear-gradient(135deg, #3b82f6, #1d4ed8)",
    "green": "linear-gradient(135deg, #10b981, #047857)",
    "yellow": "linear-gradient(135deg, #f59e0b, #b45309)",
    "purple": "linear-gradient(135deg, #8b5cf6, #6d28d9)",
    "red": "linear-gradient(135deg, #f87171, #b91c1c)",
    "cyan": "linear-gradient(135deg, #22d3ee, #0e7490)",
}
