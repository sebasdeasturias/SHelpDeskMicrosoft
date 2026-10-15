"""
Prueba de carga moderada y controlada (sin ataques): solo endpoints de solo
lectura sin coste de escritura (/api/health) y un recurso estático del frontend.

Escenarios (seguro para producción: peticiones ligeras, cortas y sin mutación):
  A) túnel API  concurrencia 4   x 60 peticiones /api/health
  B) túnel API  concurrencia 10  x 100 peticiones /api/health
  C) API local  concurrencia 10  x 100 peticiones /api/health  (base sin túnel)
  D) frontend   concurrencia 10  x 100 peticiones /login.html  (CDN)

Salida: test/datos/carga.csv y test/datos/carga_resumen.csv
Uso:    python test/scripts/carga.py
"""
import concurrent.futures as cf
import csv
import pathlib
import statistics
import ssl
import time
import urllib.request

BASE = pathlib.Path(__file__).resolve().parents[1]
DATOS = BASE / "datos"
DATOS.mkdir(parents=True, exist_ok=True)

API_TUNEL = "https://api.sistemahelpdesk.online/api/health"
API_LOCAL = "http://127.0.0.1:8000/api/health"
FRONT = "https://www.sistemahelpdesk.online/login.html"

ESCENARIOS = [
    ("A_tunel_c4", API_TUNEL, 4, 60),
    ("B_tunel_c10", API_TUNEL, 10, 100),
    ("C_local_c10", API_LOCAL, 10, 100),
    ("D_frontend_c10", FRONT, 10, 100),
    ("E_tunel_c20", API_TUNEL, 20, 100),
]

CTX = ssl.create_default_context()


def una_peticion(url):
    inicio = time.perf_counter()
    status, error = 0, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SHelpDesk-QA/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            r.read(64_000)
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    ms = (time.perf_counter() - inicio) * 1000
    return {"status": status, "ms": round(ms, 2), "error": error}


def percentil(ordenado, p):
    if not ordenado:
        return 0.0
    k = (len(ordenado) - 1) * p / 100
    i, j = int(k), min(int(k) + 1, len(ordenado) - 1)
    return ordenado[i] + (ordenado[j] - ordenado[i]) * (k - i)


def correr(nombre, url, concurrencia, total):
    print(f"-> {nombre}: {total} peticiones con concurrencia {concurrencia}")
    filas = []
    inicio = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=concurrencia) as pool:
        futuros = [pool.submit(una_peticion, url) for _ in range(total)]
        for i, fut in enumerate(cf.as_completed(futuros), 1):
            r = fut.result()
            r.update({"escenario": nombre, "url": url, "concurrencia": concurrencia})
            filas.append(r)
            if i % 25 == 0:
                print(f"   {i}/{total}")
    duracion = time.perf_counter() - inicio
    ok = [f for f in filas if f["status"] == 200]
    lat = sorted(f["ms"] for f in ok)
    resumen = {
        "escenario": nombre, "url": url, "concurrencia": concurrencia,
        "peticiones": total, "ok": len(ok), "fallos": total - len(ok),
        "tasa_fallo_pct": round(100 * (total - len(ok)) / total, 2),
        "duracion_s": round(duracion, 2),
        "rps": round(total / duracion, 2),
        "p50_ms": round(percentil(lat, 50), 1) if lat else None,
        "p95_ms": round(percentil(lat, 95), 1) if lat else None,
        "p99_ms": round(percentil(lat, 99), 1) if lat else None,
        "max_ms": round(lat[-1], 1) if lat else None,
        "media_ms": round(statistics.fmean(lat), 1) if lat else None,
        "errores_red": sum(1 for f in filas if f["error"]),
    }
    return filas, resumen


def main():
    todas, resumenes = [], []
    for nombre, url, conc, total in ESCENARIOS:
        filas, resumen = correr(nombre, url, conc, total)
        todas.extend(filas)
        resumenes.append(resumen)
        # pausa entre escenarios para no acumular carga
        time.sleep(3)
    with (DATOS / "carga.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["escenario", "url", "concurrencia",
                                          "status", "ms", "error"])
        w.writeheader()
        w.writerows(todas)
    with (DATOS / "carga_resumen.csv").open("w", newline="", encoding="utf-8") as f:
        campos = list(resumenes[0].keys())
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(resumenes)
    print("OK -> carga.csv y carga_resumen.csv")
    for r in resumenes:
        print(f"  {r['escenario']:16} rps={r['rps']:6} p50={r['p50_ms']} "
              f"p95={r['p95_ms']} p99={r['p99_ms']} fallos={r['fallos']}/{r['peticiones']}")


if __name__ == "__main__":
    main()
