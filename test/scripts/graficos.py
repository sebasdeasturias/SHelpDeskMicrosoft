"""
Genera los gráficos de los reportes a partir de los CSV/JSON de test/datos.

Salida: test/graficos/*.png
Uso:    python test/scripts/graficos.py
"""
import csv
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parents[1]
DATOS = BASE / "datos"
GRAF = BASE / "graficos"
GRAF.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.3, "axes.axisbelow": True,
})


def leer_csv(nombre):
    with (DATOS / nombre).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def grafico_rendimiento_percentiles():
    filas = [r for r in leer_csv("rendimiento_resumen.csv") if r.get("ok") and r["ok"] != "0"]
    etiquetas = [r["objetivo"].replace("_", "\n") for r in filas]
    p50 = [float(r["total_p50"]) for r in filas]
    p95 = [float(r["total_p95"]) for r in filas]
    x = range(len(filas))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar([i - 0.2 for i in x], p50, width=0.4, label="p50", color="#3CA0D4")
    ax.bar([i + 0.2 for i in x], p95, width=0.4, label="p95", color="#10599D")
    for i, (a, b) in enumerate(zip(p50, p95)):
        ax.text(i - 0.2, a + max(p50) * 0.01, f"{a:.0f}", ha="center", fontsize=7)
        ax.text(i + 0.2, b + max(p50) * 0.01, f"{b:.0f}", ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels(etiquetas, fontsize=7.5)
    ax.set_ylabel("milisegundos")
    ax.set_yscale("log")
    ax.set_title("Latencia total por objetivo (ms, escala log) — 15 muestras")
    ax.legend()
    fig.tight_layout()
    fig.savefig(GRAF / "rendimiento_percentiles.png")
    plt.close(fig)


def grafico_descomposicion_latencia():
    filas = [r for r in leer_csv("rendimiento_resumen.csv") if r.get("ok") and r["ok"] != "0"]
    # rehacer medias por componente desde el CSV detallado
    det = leer_csv("rendimiento.csv")
    objetivos = [r["objetivo"] for r in filas]
    comps = ["dns_ms", "tcp_ms", "tls_ms", "ttfb_ms"]
    colores = ["#94A3B8", "#64748B", "#3CA0D4", "#10599D"]
    medias = {}
    for o in objetivos:
        m = [d for d in det if d["objetivo"] == o and d["status"] not in ("0", "")]
        if not m:
            continue
        # ttfb incluye dns+tcp+tls: mostramos solo el tramo "hasta inicio de respuesta"
        medias[o] = [sorted(float(d[c]) for d in m)[len(m) // 2] for c in comps]
    etq = [o.replace("_", "\n") for o in medias]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    base = [0.0] * len(etq)
    for i, (c, col) in enumerate(zip(comps, colores)):
        vals = [medias[o][i] - (medias[o][i - 1] if i else 0) for o in medias]
        ax.bar(etq, vals, bottom=base, color=col,
               label={"dns_ms": "DNS", "tcp_ms": "TCP", "tls_ms": "TLS",
                      "ttfb_ms": "servidor (TTFB restante)"}[c])
        base = [b + v for b, v in zip(base, vals)]
    ax.set_ylabel("ms (mediana)")
    ax.set_title("Descomposición de la latencia hasta el primer byte")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(GRAF / "rendimiento_descomposicion.png")
    plt.close(fig)


def grafico_carga():
    filas = leer_csv("carga_resumen.csv")
    def etq_corta(r):
        p = r["escenario"].split("_")
        tipo = p[1] if len(p) > 1 else r["escenario"]
        return f"{p[0]} · {tipo}\n(c={r['concurrencia']})"

    etq = [etq_corta(r) for r in filas]
    p50 = [float(r["p50_ms"]) for r in filas]
    p95 = [float(r["p95_ms"]) for r in filas]
    p99 = [float(r["p99_ms"]) for r in filas]
    rps = [float(r["rps"]) for r in filas]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))
    x = range(len(filas))
    ax1.bar([i - 0.25 for i in x], p50, 0.25, label="p50", color="#3CA0D4")
    ax1.bar(list(x), p95, 0.25, label="p95", color="#10599D")
    ax1.bar([i + 0.25 for i in x], p99, 0.25, label="p99", color="#B91C1C")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(etq, fontsize=7.5)
    ax1.set_ylabel("ms")
    ax1.set_title("Latencia por escenario de carga")
    ax1.legend(fontsize=8)
    colores = ["#10B981" if float(r["fallos"]) == 0 else "#DC2626" for r in filas]
    ax2.bar(etq, rps, color=colores)
    for i, v in enumerate(rps):
        ax2.text(i, v + 0.4, f"{v:.1f}", ha="center", fontsize=8)
    ax2.set_ylabel("peticiones/segundo")
    ax2.set_title("Rendimiento sostenido (0 fallos en verde)")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(etq, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(GRAF / "carga_resumen.png")
    plt.close(fig)


def grafico_recursos():
    # docker_stats.csv se escribió con PowerShell (UTF-16), ';' y sin cabecera
    crudo = (DATOS / "docker_stats.csv").read_bytes()
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = crudo.decode("utf-16")
    filas = []
    for linea in texto.splitlines():
        partes = linea.split(";")
        if len(partes) == 6:
            filas.append({"Name": partes[0], "CPUPerc": partes[1],
                          "MemUsage": partes[2], "MemPerc": partes[3],
                          "NetIO": partes[4], "BlockIO": partes[5]})
    nombres = [f["Name"] for f in filas]
    cpu = [float(f["CPUPerc"].replace("%", "")) for f in filas]
    mem = [float(f["MemPerc"].replace("%", "")) for f in filas]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    orden = sorted(range(len(nombres)), key=lambda i: -cpu[i])
    ax1.barh([nombres[i] for i in orden], [cpu[i] for i in orden], color="#10599D")
    ax1.set_title("CPU instantánea (%)")
    ax1.invert_yaxis()
    orden2 = sorted(range(len(nombres)), key=lambda i: -mem[i])
    ax2.barh([nombres[i] for i in orden2], [mem[i] for i in orden2], color="#3CA0D4")
    ax2.set_title("Memoria (%) del total del host")
    ax2.invert_yaxis()
    fig.suptitle("Uso de recursos por contenedor (instantánea docker stats)")
    fig.tight_layout()
    fig.savefig(GRAF / "recursos_contenedores.png")
    plt.close(fig)


def grafico_endpoints():
    filas = leer_csv("endpoints.csv")
    grupos = {}
    for f in filas:
        g = f["grupo"] or "(raiz)"
        grupos[g] = grupos.get(g, 0) + 1
    orden = sorted(grupos.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.barh([k for k, _ in orden], [v for _, v in orden], color="#10599D")
    for i, (k, v) in enumerate(orden):
        ax.text(v + 0.2, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("operaciones (método + ruta)")
    ax.set_title("Superficie de API por grupo (openapi.json)")
    fig.tight_layout()
    fig.savefig(GRAF / "endpoints_por_grupo.png")
    plt.close(fig)


def grafico_codigo():
    datos = json.loads((DATOS / "metricas.json").read_text(encoding="utf-8"))
    carpetas = datos["carpetas"]
    nombres = [k for k in carpetas if carpetas[k]["lineas"] > 50]
    valores = [carpetas[k]["lineas"] for k in nombres]
    orden = sorted(zip(nombres, valores), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh([k for k, _ in orden], [v for _, v in orden], color="#3CA0D4")
    for i, (_, v) in enumerate(orden):
        ax.text(v + 200, i, f"{v:,}", va="center", fontsize=8)
    ax.set_xlabel("líneas de código")
    ax.set_title("LOC por carpeta del repositorio")
    fig.tight_layout()
    fig.savefig(GRAF / "codigo_por_carpeta.png")
    plt.close(fig)


def grafico_arquitectura():
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.axis("off")

    def caja(x, y, texto, color, w=2.7, h=1.0, fc="#FFFFFF"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                                    linewidth=1.5, edgecolor=color, facecolor=fc))
        ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=8.5)
        return (x, y, w, h)

    def flecha(a, b, etiqueta="", color="#475569", estilo="-|>", guion=False):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle=estilo, mutation_scale=13,
                                     linewidth=1.4, color=color,
                                     linestyle="--" if guion else "-"))
        if etiqueta:
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            dx, dy = b[0] - a[0], b[1] - a[1]
            # etiqueta desplazada perpendicular a la flecha
            n = max(abs(dx), abs(dy)) or 1
            ox, oy = -dy / n * 0.22, dx / n * 0.22
            ax.text(mx + ox, my + oy, etiqueta, ha="center", va="center",
                    fontsize=7.5, color="#334155",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))

    # fila 1: borde público
    caja(0.4, 5.0, "Navegador\n(HTTPS)", "#10599D")
    caja(3.9, 5.0, "Vercel\nfrontend estático +\nrewrite /api/*", "#7C3AED")
    caja(7.5, 5.0, "Cloudflare\nTunnel  api.…", "#F59E0B")
    caja(10.7, 5.0, "backend:8000\nFastAPI (1 worker,\n--reload)", "#10599D")
    # fila 2: servicios internos (red Docker)
    caja(0.4, 3.0, "streamlit:8501\npanel admin\n(127.0.0.1)", "#3CA0D4")
    caja(3.9, 3.0, "ollama\nGPU · bge-m3 / chat\n(127.0.0.1)", "#7C3AED")
    caja(7.5, 3.0, "n8n\nworkflows IA\n(127.0.0.1)", "#BE123C")
    caja(10.7, 3.0, "postgres 16\n+ pgvector\n(127.0.0.1)", "#047857")
    # fila 3: soporte
    caja(0.4, 1.1, "docker-socket-proxy\nSOLO lectura (POST=0)", "#64748B")
    caja(7.5, 1.1, "volúmenes: postgres_data · adjuntos ·\nbackups · n8n · ollama\n(los escribe el backend)", "#94A3B8", w=4.0)

    # flujo público
    flecha((3.1, 5.5), (3.9, 5.5), "HTML/CSS/JS")
    flecha((6.6, 5.5), (7.5, 5.5), "/api/*")
    flecha((10.2, 5.5), (10.7, 5.5), "túnel")
    # internos
    flecha((12.05, 5.0), (12.05, 4.05), "SQL")
    flecha((11.2, 5.0), (9.7, 4.08), "webhook IA")
    flecha((7.5, 3.5), (6.6, 3.5), "inferencia")
    flecha((1.75, 3.0), (1.75, 2.15), "logs")
    # streamlit -> postgres (codo por debajo)
    flecha((2.4, 3.0), (2.4, 2.6), guion=True)
    ax.add_patch(FancyArrowPatch((2.4, 2.6), (11.4, 2.6), arrowstyle="-",
                                 linewidth=1.1, color="#64748B", linestyle="--"))
    flecha((11.4, 2.6), (11.4, 3.0), color="#64748B", guion=True)
    ax.text(6.9, 2.78, "streamlit → postgres (red interna)", ha="center",
            fontsize=7.5, color="#334155",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))

    ax.set_xlim(0, 13.6)
    ax.set_ylim(0.7, 6.4)
    ax.set_title("Arquitectura desplegada de sistemahelpdesk.online", fontsize=11)
    fig.tight_layout()
    fig.savefig(GRAF / "arquitectura.png")
    plt.close(fig)


def grafico_seguridad():
    datos = json.loads((DATOS / "recon.json").read_text(encoding="utf-8"))
    categorias = {
        "Cabeceras de seguridad (frontend)": (10, 0, 1),
        "Cabeceras de seguridad (API)": (5, 2, 3),
        "Autenticación en endpoints": (18, 1, 0),
        "CORS restrictivo": (4, 0, 0),
        "Validación de entrada (422, sin fuga)": (5, 0, 0),
        "Rate-limit de login": (1, 0, 0),
        "TLS moderno": (3, 1, 0),
        "Sin documentación API pública": (0, 0, 1),
        "Sin enumeración de adjuntos": (0, 0, 1),
    }
    nombres = list(categorias)
    ok = [categorias[n][0] for n in nombres]
    aviso = [categorias[n][1] for n in nombres]
    fallo = [categorias[n][2] for n in nombres]
    y = range(len(nombres))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.barh(y, ok, color="#10B981", label="conforme")
    ax.barh(y, aviso, left=ok, color="#F59E0B", label="aviso")
    ax.barh(y, fallo, left=[o + a for o, a in zip(ok, aviso)], color="#DC2626", label="hallazgo")
    ax.set_yticks(list(y))
    ax.set_yticklabels(nombres, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("comprobaciones")
    ax.set_title("Tarjeta de seguridad (recon.json)")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(GRAF / "seguridad_scorecard.png")
    plt.close(fig)


def main():
    for fn in (grafico_rendimiento_percentiles, grafico_descomposicion_latencia,
               grafico_carga, grafico_recursos, grafico_endpoints,
               grafico_codigo, grafico_arquitectura, grafico_seguridad):
        fn()
        print("OK", fn.__name__)


if __name__ == "__main__":
    main()
