#!/usr/bin/env python3
"""Carga masiva de tickets [CARGA] contra el webhook de clasificación de n8n.

Pensado para ejecutarse DENTRO del contenedor helpdesk-backend (tiene asyncpg,
httpx y acceso a la red interna). No crea tickets: usa los que ya insertó
database/mock_tickets_por_hacer.sql y simula la ráfaga de notificaciones que
haría el backend cuando miles de usuarios envían el formulario.

Uso:
  docker cp test/load_mock_tickets.py helpdesk-backend:/tmp/load.py
  docker exec helpdesk-backend python /tmp/load.py --limit 100 --concurrency 8
  docker exec helpdesk-backend python /tmp/load.py --limit 0 --concurrency 12

  --limit 0       todos los tickets [CARGA] pendientes
  --concurrency   peticiones simultáneas al webhook
  --timeout       timeout por petición (segundos)
  --dry-run       solo muestra cuántos tickets se enviarían
"""
import argparse
import asyncio
import os
import statistics
import time
from datetime import datetime, timezone

import asyncpg
import httpx

PREFIJO = "[CARGA] "
DB_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
N8N_URL = os.environ.get("N8N_URL", "http://n8n:5678").rstrip("/")
WEBHOOK = f"{N8N_URL}/webhook/new-ticket"


def payload_ticket(row):
    asunto = row["asunto"]
    if asunto.startswith(PREFIJO):
        asunto = asunto[len(PREFIJO):]
    return {
        "event": "new_ticket_created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_id": row["id_solicitud"],
        "ticket": {
            "asunto": asunto,
            "descripcion": row["descripcion"],
            "categoria": {"id": row["id_categoria"], "nombre": row["categoria"]},
            "prioridad": {"id": row["id_prioridad"], "nombre": row["prioridad"]},
            "estado": "nuevo",
            "fecha_creacion": datetime.now(timezone.utc).isoformat(),
        },
        "solicitante": {
            "id": row["id_usuario"],
            "nombre": row["nombre"],
            "email": row["email"],
            "area": row["area"],
        },
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100,
                        help="0 = todos los tickets [CARGA] pendientes")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch(
            """
            SELECT s.id_solicitud, s.asunto, s.descripcion,
                   s.id_categoria, c.nombre AS categoria,
                   s.id_prioridad, p.nivel AS prioridad,
                   u.id_usuario, u.nombre, u.email, u.area
            FROM solicitud s
            JOIN usuarios u ON u.id_usuario = s.id_solicitante
            LEFT JOIN categoria c ON c.id_categoria = s.id_categoria
            LEFT JOIN prioridad p ON p.id_prioridad = s.id_prioridad
            WHERE s.asunto LIKE '[CARGA]%' AND s.estado = 'nuevo'
              AND NOT EXISTS (
                  SELECT 1 FROM clasificacion_ia ci
                  WHERE ci.id_solicitud = s.id_solicitud
              )
            ORDER BY s.id_solicitud
            LIMIT $1
            """,
            args.limit if args.limit > 0 else 2147483647,
        )
        if not rows:
            print("No hay tickets [CARGA] pendientes. Ejecuta mock_tickets_por_hacer.sql.")
            return

        ids = [r["id_solicitud"] for r in rows]
        print(f"Tickets a enviar: {len(rows)}  |  concurrencia: {args.concurrency}")
        if args.dry_run:
            return

        # Limpiar clasificaciones previas de esta tanda para medir desde cero.
        await conn.execute(
            "DELETE FROM clasificacion_ia WHERE id_solicitud = ANY($1::int[])", ids
        )

        sem = asyncio.Semaphore(max(1, args.concurrency))
        lock = asyncio.Lock()
        results = []
        done = 0
        started = time.perf_counter()

        async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout)) as client:
            async def enviar(row):
                nonlocal done
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        resp = await client.post(WEBHOOK, json=payload_ticket(row))
                        elapsed = time.perf_counter() - t0
                        ok = resp.status_code == 200
                        body = resp.text[:300] if not ok else ""
                    except Exception as exc:  # noqa: BLE001
                        elapsed = time.perf_counter() - t0
                        ok = False
                        body = f"{type(exc).__name__}: {exc}"[:300]
                    async with lock:
                        results.append((row["id_solicitud"], ok, elapsed, body))
                        done += 1
                        if done % 25 == 0 or done == len(rows):
                            print(f"  {done}/{len(rows)} enviados...", flush=True)

            await asyncio.gather(*(enviar(r) for r in rows))

        total_elapsed = time.perf_counter() - started
        ok_count = sum(1 for _, ok, _, _ in results if ok)
        fail = [r for r in results if not r[1]]
        latencias = [r[2] for r in results if r[1]]

        print("\n=== RESULTADO DE CARGA ===")
        print(f"Tickets enviados : {len(results)}")
        print(f"Webhook 200      : {ok_count}")
        print(f"Fallos           : {len(fail)}")
        print(f"Tiempo total     : {total_elapsed:.1f} s")
        print(f"Throughput       : {len(results) / total_elapsed:.2f} tickets/s")
        if latencias:
            latencias.sort()
            p50 = statistics.median(latencias)
            p95 = latencias[min(len(latencias) - 1, int(len(latencias) * 0.95))]
            print(f"Latencia p50/p95 : {p50:.2f} s / {p95:.2f} s")

        clasificadas = await conn.fetchval(
            "SELECT count(*) FROM clasificacion_ia WHERE id_solicitud = ANY($1::int[])",
            ids,
        )
        confianza = await conn.fetchval(
            "SELECT avg(confianza) FROM clasificacion_ia WHERE id_solicitud = ANY($1::int[])",
            ids,
        )
        print(f"Clasificadas en BD: {clasificadas}/{len(ids)}")
        if confianza is not None:
            print(f"Confianza media   : {float(confianza):.3f}")

        if fail:
            print("\nPrimeros fallos:")
            for tid, _, _, body in fail[:10]:
                print(f"  #{tid}: {body}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
