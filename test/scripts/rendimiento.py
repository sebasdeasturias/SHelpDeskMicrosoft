"""
Mediciones de rendimiento extremo a extremo (percentiles, TTFB, cache).

MÃ©tricas por peticiÃ³n (curl.exe, que ademÃ¡s negocia HTTP/2 con Vercel/Cloudflare):
  dns_ms, tcp_ms, tls_ms, ttfb_ms, total_ms, status, bytes, velocidad_bps

Objetivos:
  - frontend estÃ¡tico (Vercel, con CDN)
  - API vÃ­a tÃºnel Cloudflare
  - backend local en 127.0.0.1:8000 (lÃ­nea base sin tÃºnel)

Salida: test/datos/rendimiento.csv y test/datos/rendimiento_resumen.csv
Uso:    python test/scripts/rendimiento.py [muestras]
"""
import csv
import pathlib
import statistics
import subprocess
import sys
import time

BASE = pathlib.Path(__file__).resolve().parents[1]
DATOS = BASE / "datos"
DATOS.mkdir(parents=True, exist_ok=True)

FORMATO = ("%{time_namelookup},%{time_connect},%{time_appconnect},"
           "%{time_starttransfer},%{time_total},%{http_code},%{size_download},"
           "%{speed_download},%{ssl_verify_result},%{num_connects}")

OBJETIVOS = [
    ("frontend_inicio", "https://www.sistemahelpdesk.online/"),
    ("frontend_login", "https://www.sistemahelpdesk.online/login.html"),
    ("frontend_css", "https://www.sistemahelpdesk.online/styles/login.css"),
    ("frontend_js_config", "https://www.sistemahelpdesk.online/js/config.js"),
    ("frontend_logo_grande", "https://www.sistemahelpdesk.online/logohelpdesk.png"),
    ("api_health_tunel", "https://api.sistemahelpdesk.online/api/health"),
    ("api_openapi_tunel", "https://api.sistemahelpdesk.online/openapi.json"),
    ("api_health_local", "http://127.0.0.1:8000/api/health"),
    ("apex_redireccion", "https://sistemahelpdesk.online/"),
]


def medir(url):
    """Una muestra con curl.exe; devuelve las mÃ©tricas en milisegundos."""
    cmd = ["curl.exe", "-sS", "-o", "NUL", "--max-time", "25", "--connect-timeout", "8",
           "-H", "User-Agent: SHelpDesk-QA/1.0",
           "-w", FORMATO, url]
    try:
        salida = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        partes = (salida.stdout or "").strip().split(",")
        if len(partes) != 10:
            return None
        dns, tcp, tls, ttfb, total, code, size, speed, ssl_ok, nconn = partes
        return {
            "dns_ms": float(dns) * 1000,
            "tcp_ms": float(tcp) * 1000,
            "tls_ms": float(tls) * 1000,
            "ttfb_ms": float(ttfb) * 1000,
            "total_ms": float(total) * 1000,
            "status": int(code),
            "bytes": int(float(size)),
            "velocidad_bps": float(speed),
            "ssl_ok": int(float(ssl_ok)),
            "conexiones": int(float(nconn)),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "status": 0}


def percentil(ordenado, p):
    if not ordenado:
        return 0.0
    k = (len(ordenado) - 1) * p / 100
    inf, sup = int(k), min(int(k) + 1, len(ordenado) - 1)
    return ordenado[inf] + (ordenado[sup] - ordenado[inf]) * (k - inf)


def resumir(muestras):
    ok = [m for m in muestras if m.get("status") and 0 < m["status"] < 400]
    if not ok:
        return {"n": len(muestras), "ok": 0}
    totales = sorted(m["total_ms"] for m in ok)
    ttfb = sorted(m["ttfb_ms"] for m in ok)
    return {
        "n": len(muestras), "ok": len(ok), "fallos": len(muestras) - len(ok),
        "status_tipico": statistics.mode([m["status"] for m in ok]),
        "total_min": round(totales[0], 1),
        "total_p50": round(percentil(totales, 50), 1),
        "total_p95": round(percentil(totales, 95), 1),
        "total_max": round(totales[-1], 1),
        "total_media": round(statistics.fmean(totales), 1),
        "ttfb_p50": round(percentil(ttfb, 50), 1),
        "ttfb_p95": round(percentil(ttfb, 95), 1),
        "bytes": ok[0]["bytes"],
        "velocidad_media_bps": int(statistics.fmean([m["velocidad_bps"] for m in ok if m["velocidad_bps"] > 0]) or 0),
    }


def main():
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    filas = []
    for nombre, url in OBJETIVOS:
        print(f"-> {nombre} ({muestras} muestras)")
        for i in range(muestras):
            m = medir(url)
            if m is None:
                continue
            m.update({"objetivo": nombre, "url": url, "muestra": i + 1})
            filas.append(m)
            time.sleep(0.12)
    campos = ["objetivo", "url", "muestra", "status", "dns_ms", "tcp_ms", "tls_ms",
              "ttfb_ms", "total_ms", "bytes", "velocidad_bps", "ssl_ok", "conexiones"]
    with (DATOS / "rendimiento.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    resumen = []
    for nombre, url in OBJETIVOS:
        r = resumir([f for f in filas if f["objetivo"] == nombre])
        r.update({"objetivo": nombre, "url": url})
        resumen.append(r)
    with (DATOS / "rendimiento_resumen.csv").open("w", newline="", encoding="utf-8") as f:
        campos_r = ["objetivo", "url", "n", "ok", "fallos", "status_tipico", "bytes",
                    "total_min", "total_p50", "total_p95", "total_max", "total_media",
                    "ttfb_p50", "ttfb_p95", "velocidad_media_bps"]
        w = csv.DictWriter(f, fieldnames=campos_r, extrasaction="ignore")
        w.writeheader()
        w.writerows(resumen)
    print("OK ->", DATOS / "rendimiento.csv", "y rendimiento_resumen.csv")
    for r in resumen:
        if r.get("ok"):
            print(f"  {r['objetivo']:22} p50={r['total_p50']:7.1f} ms  "
                  f"p95={r['total_p95']:7.1f} ms  ttfb_p50={r['ttfb_p50']:6.1f} ms  "
                  f"({r['ok']}/{r['n']})")


if __name__ == "__main__":
    main()

