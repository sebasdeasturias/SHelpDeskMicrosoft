#!/usr/bin/env python3
"""Benchmark completo por módulos — familia ISO/IEC 25000.

Flujo:
  1. Verifica que el stack esté montado (./iniciar.sh).
  2. Siembra usuarios MOCK y el corpus de tickets.
  3. Ejecuta los escenarios de carga por módulo (benchmark/runner.py).
  4. Evalúa con ISO/IEC 25010/25012/25023/25040 (benchmark/iso25000.py).
  5. Genera el informe en Test/reports/benchmark_iso25000.{json,md}.

Uso:
    python3 Test/run_benchmark.py [--sin-mocks]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

from scan import collect_all  # noqa: E402
from benchmark.mocks import seed_mock_users, seed_corpus_tickets  # noqa: E402
from benchmark.runner import run_all, API  # noqa: E402
from benchmark.iso25000 import evaluar_todo  # noqa: E402
from benchmark.report import generar_informe  # noqa: E402


def stack_arriba() -> bool:
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=15)
        nombres = set(r.stdout.split())
        return {"helpdesk-db", "helpdesk-backend"} <= nombres
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sin-mocks", action="store_true",
                    help="No crear usuarios mock (asume que ya existen)")
    args = ap.parse_args()

    print("=" * 72)
    print("Benchmark de calidad — Familia ISO/IEC 25000")
    print(f"API: {API}")
    print(f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print("=" * 72)

    if not stack_arriba():
        print("ERROR: el stack no está montado (faltan helpdesk-db/helpdesk-backend).")
        print("       Ejecuta primero: ./iniciar.sh")
        return 2

    if not args.sin_mocks:
        print("[1/4] Sembrando usuarios mock y corpus de tickets...")
        inv = seed_mock_users()
        print(f"      {inv['total']} usuarios mock por rol: "
              f"{', '.join(f'{r}={len(u)}' for r, u in inv['por_rol'].items())}")
        creados = seed_corpus_tickets()
        print(f"      corpus tickets nuevos: {creados}")
    else:
        print("[1/4] Mocks: se reutilizan los existentes")
        inv = seed_mock_users()  # idempotente: solo refresca estado

    print("[2/4] Ejecutando escenarios de benchmark...")
    datos = run_all(inv)

    print("[3/4] Evaluando con ISO/IEC 25010/25012/25023/25040...")
    estaticas = collect_all()
    evaluacion = evaluar_todo(datos, estaticas)

    print("[4/4] Generando informe...")
    json_path, md_path = generar_informe(datos, evaluacion, estaticas)

    print()
    print("RESUMEN POR NORMA (familia ISO/IEC 25000)")
    for clave, b in evaluacion["familia"].items():
        print(f"  {b['norma']:<55} score={b.get('score'):>6}  {b.get('veredicto')}")
    print()
    print("RESUMEN POR MÓDULO")
    for nombre, m in sorted(evaluacion["modulos"].items(),
                            key=lambda kv: -(kv[1].get("score_modulo") or 0)):
        print(f"  {nombre:<16} score={str(m.get('score_modulo')):>6}  {m.get('veredicto')}")
    print()
    print(f"Informe JSON : {json_path}")
    print(f"Informe MD   : {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
