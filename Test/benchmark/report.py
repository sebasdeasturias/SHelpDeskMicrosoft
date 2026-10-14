"""Generación del informe de calidad (JSON + Markdown) en Test/reports/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from ..config import REPORTS_DIR
except ImportError:  # ejecución como paquete top-level desde Test/
    from config import REPORTS_DIR

NOMBRE_JSON = "benchmark_iso25000.json"
NOMBRE_MD = "benchmark_iso25000.md"


def _tabla_escenarios(escenarios: list[dict]) -> list[str]:
    lineas = [
        "| Escenario | Método | n | Conc. | OK% | P50 (ms) | P95 (ms) | P99 (ms) | RPS | Tiempo |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for e in escenarios:
        lat = e.get("latencia", {})
        lineas.append(
            f"| {e['escenario']} | {e['metodo']} | {lat.get('n', e.get('muestreo', 0))} "
            f"| {e.get('concurrencia', 1)} | {e.get('tasa_ok', 0)*100:.0f}% "
            f"| {lat.get('p50_ms', '—')} | {lat.get('p95_ms', '—')} "
            f"| {lat.get('p99_ms', '—')} | {e.get('throughput_rps', 0)} "
            f"| {e.get('clasificacion_tiempo', e.get('latencia', {}).get('clasificacion_tiempo', '—'))} |"
        )
    return lineas


def _tabla_modulos(modulos: dict) -> list[str]:
    lineas = [
        "| Módulo | Score ISO/IEC 25010 | Veredicto |",
        "|---|---:|---|",
    ]
    for nombre, m in sorted(modulos.items(), key=lambda kv: -(kv[1].get("score_modulo") or 0)):
        lineas.append(f"| {nombre} | {m.get('score_modulo', '—')} | {m.get('veredicto', '—')} |")
    return lineas


def _tabla_caracteristicas(familia: dict) -> list[str]:
    fam = familia.get("ISO_IEC_25010", {}).get("caracteristicas", {})
    lineas = ["| Característica ISO/IEC 25010:2023 | Score medio |", "|---|---:|"]
    for k, v in fam.items():
        lineas.append(f"| {k.replace('_', ' ')} | {v} |")
    return lineas


def generar_informe(datos: dict, evaluacion: dict, estaticas: dict) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc = {
        "fecha_utc": fecha,
        "raiz": str(Path(__file__).resolve().parents[2]),
        "metodo": {
            "familia_normas": [
                "ISO/IEC 25000:2014 (SQuaRE — guía)",
                "ISO/IEC 25010:2023 (modelo de calidad de producto)",
                "ISO/IEC 25012:2008 (calidad de datos)",
                "ISO/IEC 25023:2016 (métricas de producto)",
                "ISO/IEC 25040:2011 (proceso de evaluación)",
            ],
            "principio": "Benchmark de runtime con usuarios mock sobre los "
                         "contenedores montados con iniciar.sh. Sin "
                         "auto-declaraciones: todas las métricas se miden.",
            "umbrales": evaluacion["umbrales"],
            "usuarios_mock": datos.get("usuarios_mock"),
            "tokens_emitidos": datos.get("tokens_emitidos"),
        },
        "familia_iso_25000": evaluacion["familia"],
        "modulos": evaluacion["modulos"],
        "resultados_crudos": datos.get("escenarios", {}),
        "verificaciones_custom": datos.get("custom", {}),
        "metricas_estaticas": {
            k: v for k, v in (estaticas or {}).items()
            if k not in ("corpus_py", "corpus_all")
        },
    }

    json_path = REPORTS_DIR / NOMBRE_JSON
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    md = _markdown(doc, datos, evaluacion)
    md_path = REPORTS_DIR / NOMBRE_MD
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def _markdown(doc: dict, datos: dict, evaluacion: dict) -> str:
    m = doc["metodo"]
    fam = evaluacion["familia"]
    L: list[str] = []
    a = L.append

    a("# Informe de benchmark de calidad — Familia ISO/IEC 25000")
    a("")
    a(f"**Sistema:** SHelpDesk Microsoft  ")
    a(f"**Fecha (UTC):** {doc['fecha_utc']}  ")
    a(f"**Usuarios mock:** {m['usuarios_mock']}  ")
    a(f"**Principio:** {m['principio']}")
    a("")
    a("## 1. Umbrales de evaluación (ISO/IEC 25023, declarados a priori)")
    a("")
    u = m["umbrales"]
    a(f"- Lectura API: P95 ≤ **{u['lectura_p95_bien_ms']} ms** (bien) / "
      f"≤ {u['lectura_p95_aceptable_ms']} ms (aceptable)")
    a(f"- Escritura API: P95 ≤ **{u['escritura_p95_bien_ms']} ms** (bien) / "
      f"≤ {u['escritura_p95_aceptable_ms']} ms (aceptable)")
    a(f"- Disponibilidad objetivo: **{u['disponibilidad_objetivo']*100:.1f}%**")
    a(f"- Tasa de error objetivo: **≤ {u['tasa_error_objetivo']*100:.1f}%**")
    a("")
    a("## 2. Veredicto por norma de la familia")
    a("")
    a("| Norma | Score | Veredicto |")
    a("|---|---:|---|")
    for clave in ("ISO_IEC_25000", "ISO_IEC_25010", "ISO_IEC_25012",
                  "ISO_IEC_25023", "ISO_IEC_25040"):
        b = fam[clave]
        a(f"| {b['norma']} | {b.get('score', '—')} | {b.get('veredicto', '—')} |")
    a("")
    a("## 3. Score por módulo del sistema")
    a("")
    L.extend(_tabla_modulos(evaluacion["modulos"]))
    a("")
    a("## 4. Características ISO/IEC 25010:2023 (medias de todos los módulos)")
    a("")
    L.extend(_tabla_caracteristicas(fam))
    a("")
    a("## 5. Mediciones por módulo (ISO/IEC 25023)")
    a("")
    for i, (modulo, ev) in enumerate(sorted(evaluacion["modulos"].items()), 1):
        escs_crudos = (datos.get("escenarios", {}).get(modulo, [])
                       or ev.get("escenarios_crudos", []))
        a(f"### 5.{i} Módulo `{modulo}` — score {ev.get('score_modulo')} "
          f"({ev.get('veredicto')})")
        a("")
        if escs_crudos:
            L.extend(_tabla_escenarios(escs_crudos))
            a("")
        elif ev.get("iso_25010_caracteristicas"):
            for k, c in ev["iso_25010_caracteristicas"].items():
                a(f"- **{k}**: {c['score']} — {c['evidencia']}")
            a("")
        if ev.get("nota"):
            a(f"> {ev['nota']}")
            a("")
    a("## 6. Calidad de datos (ISO/IEC 25012)")
    a("")
    d12 = fam.get("ISO_IEC_25012", {})
    a(f"**Veredicto:** {d12.get('veredicto')} (score {d12.get('score')})")
    a("")
    for k, v in (d12.get("checks") or {}).items():
        a(f"- {'✅' if v else '❌'} `{k}`")
    a("")
    a("## 7. Proceso de evaluación (ISO/IEC 25040)")
    a("")
    d40 = fam.get("ISO_IEC_25040", {})
    a(f"**Veredicto:** {d40.get('veredicto')} (score {d40.get('score')}) — "
      f"{d40.get('muestras_totales', 0)} muestras.")
    a("")
    a("## 8. Controles de seguridad ejecutados en runtime")
    a("")
    seg = datos.get("custom", {}).get("seguridad_auth", {})
    for k, v in seg.items():
        if k == "login_malo_status":
            v = ", ".join(str(x) for x in v)
        a(f"- `{k}`: {v}")
    a("")
    a("## 9. Infraestructura medida")
    a("")
    infra = datos.get("custom", {}).get("infraestructura", {})
    for nombre, estado in (infra.get("containers") or {}).items():
        a(f"- `{nombre}`: {estado}")
    hb = infra.get("health_body") or {}
    if hb:
        a(f"- `/api/health`: `{hb.get('status')}` — checks: `{hb.get('checks')}`")
    ext = datos.get("custom", {}).get("ia_externa", {})
    a("")
    a("## 10. Dependencias IA externas")
    a("")
    for nombre, info in ext.items():
        a(f"- `{nombre}`: {info}")
    a("")
    fe = datos.get("custom", {}).get("frontend", {})
    a("## 11. Frontend (métricas de activos)")
    a("")
    a(f"- Archivos: {fe.get('archivos')} — peso total: {fe.get('peso_total_kb')} KB — "
      f"páginas HTML: {fe.get('paginas_html')} — handlers inline: {fe.get('handlers_inline')}")
    a("")
    a("---")
    a("")
    a("*Generado por `Test/run_benchmark.py` (suite ISO/IEC 25000 del repositorio).*")
    a("")
    return "\n".join(L)
