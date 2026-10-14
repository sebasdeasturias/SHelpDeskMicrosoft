#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import REPORTS_DIR, ROOT
from scan import collect_all
from itil_eval import evaluar as evaluar_itil
from iso_eval import evaluar_todas


def _sin_corpus(d):
    if isinstance(d, dict):
        return {k: _sin_corpus(v) for k, v in d.items() if k not in ("corpus_py", "corpus_all")}
    if isinstance(d, list):
        return [_sin_corpus(x) for x in d]
    return d


def _linea_veredicto(nombre, bloque):
    if not isinstance(bloque, dict):
        return
    ver = bloque.get("veredicto")
    score = bloque.get("score")
    apl = bloque.get("aplicable")
    if ver is None and "veredicto" not in bloque:
        return
    score_txt = "—" if score is None else f"{score:>6}"
    apl_txt = "N/A" if apl is False else "SÍ"
    print(f"  {nombre:<42} {apl_txt:^4} {score_txt:>8}  {ver}")


def informe_texto(doc: dict) -> str:
    lineas = []
    a = lineas.append
    a("SHelpDesk — Evaluación ITIL / ISO (métricas reales de código)")
    a("=" * 72)
    a(f"Fecha UTC: {doc['fecha_utc']}")
    a(f"Raíz: {doc['raiz']}")
    a("")
    size = doc["metricas"]["size"]
    py = doc["metricas"]["python"]
    sch = doc["metricas"]["schema"]
    a("1. Tamaño del producto")
    a(f"   Archivos fuente: {size['files']}")
    a(f"   LOC no vacías:   {size['loc']}")
    a(f"   Python LOC:      {py['loc']}  funciones={py['functions']}  CC media={py['avg_cc']}  CC máx={py['max_cc']}")
    a(f"   Tablas:          {sch['table_count']}  CHECK={sch['checks']}  FK={sch['foreign_keys']}  IDX={sch['indexes']}")
    a(f"   Endpoints:       {doc['metricas']['endpoints']['count']}")
    a(f"   SQL parametrizado: {py['sql_param_ratio']}")
    a("")
    itil = doc["itil"]
    a("2. ITIL 4")
    a(f"   {itil['veredicto']}")
    a(f"   Score núcleo mesa de servicio: {itil['score_nucleo']}%")
    a(f"   Score complementarias:         {itil['score_complementarias']}%")
    a(f"   Score producto helpdesk:       {itil['score_producto_helpdesk']}%")
    a(f"   Score ITIL 4 completo:         {itil['score_itil4_34_practicas']}%  (no es implementación completa)")
    a(f"   {itil['nota']}")
    a("")
    a("   Prácticas:")
    for p in itil["practicas"]:
        a(f"   - [{p['estado']:16}] {p['nombre']}  evidencia={p['nivel_evidencia']}")
    a("")
    a("3. Normas ISO")
    iso = doc["iso"]
    for clave in (
        "ISO_IEC_25000", "ISO_IEC_25010", "ISO_IEC_25012", "ISO_IEC_25023",
        "ISO_IEC_25040", "ISO_IEC_12207", "ISO_IEC_15504_33000",
        "ISO_IEC_IEEE_29119", "ISO_IEC_27001", "ISO_IEC_20000_1",
    ):
        b = iso[clave]
        a(f"   {b['norma']}")
        a(f"      veredicto={b['veredicto']}  score={b.get('score')}  aplicable={b.get('aplicable')}")
        if b.get("nota"):
            a(f"      {b['nota']}")
    fam = iso["ISO_9000_9001_9004_19011"]
    a("   Familia ISO 9000:")
    for k, b in fam.items():
        a(f"      {b['norma']}: {b['veredicto']}")
        if b.get("nota"):
            a(f"         {b['nota']}")
    a("")
    a("4. Normas sectoriales (no aplicables al producto)")
    for b in iso["normas_sectoriales_no_aplicables"].values():
        a(f"   {b['norma']}: {b['veredicto']}")
        a(f"      {b.get('motivo') or b.get('nota')}")
    a("")
    a("5. Conclusión")
    a("   SHelpDesk SÍ cumple el perfil ITIL de mesa de servicio (incidentes,")
    a("   peticiones, SLA, conocimiento, medición). NO cumple ITIL 4 completo")
    a("   ni es certificable ISO 9001 / 20000-1 / 27001. Las normas 13485,")
    a("   IATF 16949, AS9100, 22000 y 17025 NO APLICAN a este software.")
    a("   La calidad de producto (ISO/IEC 25010/25012/25023) se mide en este")
    a("   informe con datos del código, no con declaraciones.")
    a("")
    return "\n".join(lineas) + "\n"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bruto = collect_all()
    itil = evaluar_itil(bruto["corpus_all"])
    iso = evaluar_todas(bruto, itil)
    metricas = _sin_corpus(bruto)
    doc = {
        "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raiz": str(ROOT),
        "metodo": {
            "normas": [
                "ITIL 4", "ISO 9000", "ISO 9001", "ISO 9004", "ISO 19011",
                "ISO/IEC 25000", "ISO/IEC 25010", "ISO/IEC 25012", "ISO/IEC 25023",
                "ISO/IEC 25040", "ISO/IEC 12207", "ISO/IEC 15504", "ISO/IEC 33000",
                "ISO/IEC/IEEE 29119-1", "ISO/IEC/IEEE 29119-2", "ISO/IEC/IEEE 29119-3",
                "ISO/IEC/IEEE 29119-4", "ISO/IEC 27001", "ISO/IEC 20000-1",
                "ISO 13485", "IATF 16949", "AS9100", "ISO 22000", "ISO/IEC 17025",
            ],
            "tecnicas_29119_4": [
                "particion_equivalencia",
                "valores_limite",
                "tabla_decision",
                "transicion_estados",
                "analisis_estatico",
            ],
            "principio": "Solo evidencia presente en el código y el esquema. Sin inventar certificaciones.",
        },
        "metricas": metricas,
        "itil": itil,
        "iso": iso,
    }
    json_path = REPORTS_DIR / "informe.json"
    txt_path = REPORTS_DIR / "informe.txt"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    texto = informe_texto(doc)
    txt_path.write_text(texto, encoding="utf-8")
    print(texto)
    print("Resumen de veredictos")
    print(f"  {'Norma':<42} {'Apl':^4} {'Score':>8}  Veredicto")
    print("  " + "-" * 70)
    print(f"  {'ITIL 4 mesa de servicio':<42} {'SÍ':^4} {itil['score_producto_helpdesk']:>8}  {itil['veredicto'][:48]}")
    for clave in (
        "ISO_IEC_25000", "ISO_IEC_25010", "ISO_IEC_25012", "ISO_IEC_25023",
        "ISO_IEC_25040", "ISO_IEC_12207", "ISO_IEC_15504_33000",
        "ISO_IEC_IEEE_29119", "ISO_IEC_27001", "ISO_IEC_20000_1",
    ):
        _linea_veredicto(iso[clave]["norma"][:42], iso[clave])
    print(f"Informe JSON: {json_path}")
    print(f"Informe texto: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
