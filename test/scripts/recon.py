"""
Reconocimiento no invasivo de sistemahelpdesk.online (frontend Vercel + API Cloudflare).

Todas las peticiones son de solo lectura salvo:
  - POST /api/auth/login con credenciales incorrectas (para medir rate-limit, tope 12 intentos)
  - POST /api/auth/login con payloads inválidos (validación de esquema)
No se envían escrituras reales (tickets, usuarios, etc.).

Salida: test/datos/recon.json
Uso:    python test/scripts/recon.py
"""
import json
import pathlib
import ssl
import time
import urllib.error
import urllib.request

BASE = pathlib.Path(__file__).resolve().parents[1]
DATOS = BASE / "datos"
DATOS.mkdir(parents=True, exist_ok=True)

FRONT = "https://www.sistemahelpdesk.online"
APEX = "https://sistemahelpdesk.online"
API = "https://api.sistemahelpdesk.online"

UA = "SHelpDesk-QA/1.0 (auditoría local, solo lectura)"

CABECERAS_INTERES = [
    "server", "strict-transport-security", "content-security-policy",
    "x-frame-options", "x-content-type-options", "referrer-policy",
    "permissions-policy", "cross-origin-opener-policy",
    "cross-origin-resource-policy", "x-powered-by", "age", "cf-cache-status",
    "x-vercel-cache", "cache-control", "access-control-allow-origin",
    "access-control-allow-credentials", "vary", "content-length",
]


def peticion(url, metodo="GET", headers=None, data=None, timeout=20):
    """Devuelve status, cabeceras de interés, cuerpo (recortado) y tiempos."""
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    cuerpo = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=cuerpo, headers=h, method=metodo)
    ctx = ssl.create_default_context()
    inicio = time.perf_counter()
    salida = {"url": url, "metodo": metodo, "status": None, "cabeceras": {},
              "cuerpo": "", "bytes": 0, "ms": 0.0, "error": None}
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            bruto = r.read(200_000)
            salida["status"] = r.status
            bajado = {k.lower(): v for k, v in r.headers.items()}
            salida["cabeceras"] = {k: bajado.get(k, "") for k in CABECERAS_INTERES if k in bajado}
            salida["cabeceras"]["_all"] = sorted(bajado.keys())
            salida["bytes"] = len(bruto)
            salida["cuerpo"] = bruto.decode("utf-8", "replace")[:1500]
    except urllib.error.HTTPError as e:
        salida["status"] = e.code
        bruto = e.read(200_000)
        bajado = {k.lower(): v for k, v in e.headers.items()}
        salida["cabeceras"] = {k: bajado.get(k, "") for k in CABECERAS_INTERES if k in bajado}
        salida["cabeceras"]["_all"] = sorted(bajado.keys())
        salida["bytes"] = len(bruto)
        salida["cuerpo"] = bruto.decode("utf-8", "replace")[:1500]
    except Exception as e:  # noqa: BLE001 - queremos registrar cualquier fallo
        salida["error"] = f"{type(e).__name__}: {e}"
    salida["ms"] = round((time.perf_counter() - inicio) * 1000, 2)
    time.sleep(0.25)
    return salida


def seccion_cabeceras():
    urls = [
        f"{APEX}/", f"{FRONT}/", f"{FRONT}/login.html",
        f"{FRONT}/styles/login.css", f"{FRONT}/js/config.js",
        f"{API}/api/health", f"{API}/", f"{API}/openapi.json",
        f"{API}/docs",
    ]
    return [peticion(u) for u in urls]


def seccion_exposicion():
    rutas = [
        "/.env", "/api/.env", "/.git/config", "/api/.git/config",
        "/robots.txt", "/sitemap.xml", "/security.txt", "/.well-known/security.txt",
        "/.well-known/assetlinks.json", "/vercel.json", "/docker-compose.yml",
        "/api/health", "/api/coordinator/logs/helpdesk-backend",
        "/api/coordinator/bd/tablas", "/admin", "/phpmyadmin", "/server-status",
        "/.DS_Store", "/backup.sql", "/api/openapi.json", "/openapi.json",
        "/docs", "/redoc",
    ]
    out = []
    for base in (FRONT, API):
        for r in rutas:
            res = peticion(base + r)
            res["base"] = base
            out.append({k: res[k] for k in ("base", "url", "metodo", "status", "bytes", "ms", "error")})
    return out


def seccion_auth():
    """GET protegidos sin token y con token inválido: deben dar 401/403, nunca 200."""
    protegidos = [
        "/api/tickets", "/api/auth/me", "/api/chat/health",
        "/api/chat-global/mensajes", "/api/chat-privado/contactos",
        "/api/chat-privado/no-leidos", "/api/coordinator/usuarios",
        "/api/coordinator/estadisticas", "/api/coordinator/respaldos",
        "/api/coordinator/logs/helpdesk-backend", "/api/coordinator/bd/tablas",
        "/api/coordinator/agentes", "/api/coordinator/sla", "/api/coordinator/ia",
        "/api/coordinator/n8n/workflows", "/api/coordinator/rag",
        "/api/tickets/1", "/api/tickets/1/adjuntos",
        "/api/adjuntos-archivos/prueba.txt",
    ]
    out = []
    for ruta in protegidos:
        sin = peticion(API + ruta)
        mal = peticion(API + ruta, headers={"Authorization": "Bearer token-invalido-123"})
        out.append({
            "ruta": ruta,
            "sin_token": sin["status"],
            "token_invalido": mal["status"],
            "cuerpo_sin_token": (sin["cuerpo"] or "")[:120],
            "vulnerabilidad": sin["status"] == 200 or mal["status"] == 200,
        })
    return out


def seccion_cors():
    legit = FRONT
    casos = [
        ("origen_legitimo", legit),
        ("origen_ajeno", "https://evil.example"),
        ("origen_null", "null"),
        ("origen_subdominio_ajeno", "https://sistemahelpdesk.online.evil.com"),
    ]
    out = []
    for nombre, origen in casos:
        get = peticion(f"{API}/api/health", headers={"Origin": origen})
        pre = peticion(f"{API}/api/auth/login", metodo="GET", headers={"Origin": origen})
        out.append({
            "caso": nombre, "origen": origen,
            "get_acao": get["cabeceras"].get("access-control-allow-origin", ""),
            "get_acac": get["cabeceras"].get("access-control-allow-credentials", ""),
            "get_status": get["status"],
            "preflight_status": pre["status"],
            "preflight_acao": pre["cabeceras"].get("access-control-allow-origin", ""),
            "preflight_allow_methods": pre["cabeceras"].get("access-control-allow-methods", ""),
            "todos_headers_get": get["cabeceras"].get("_all", []),
        })
    return out


def seccion_metodos():
    out = []
    for ruta in ("/api/tickets", "/api/auth/login"):
        res = peticion(API + ruta, metodo="OPTIONS",
                       headers={"Origin": FRONT, "Access-Control-Request-Method": "POST"})
        out.append({"ruta": ruta, "status": res["status"],
                    "headers": {k: v for k, v in res["cabeceras"].items() if k != "_all"},
                    "todos": res["cabeceras"].get("_all", [])})
    return out


def seccion_validacion():
    casos = [
        ("json_invalido", f"{API}/api/auth/login", "application/json", "{esto no es json}"),
        ("sql_injection_email", f"{API}/api/auth/login", "application/json",
         json.dumps({"email": "' OR '1'='1' --", "password": "x"})),
        ("sin_campos", f"{API}/api/auth/login", "application/json", "{}"),
        ("cuerpo_hinchado", f"{API}/api/auth/login", "application/json",
         json.dumps({"email": "a@" + "b" * 4000 + ".com", "password": "x" * 5000})),
        ("xss_reflejado_query", f"{API}/api/tickets?q=<script>alert(1)</script>", None, None),
    ]
    out = []
    for nombre, url, ctype, cuerpo in casos:
        if cuerpo is None:
            res = peticion(url, headers={"Authorization": "Bearer token-invalido-123"})
        else:
            res = peticion(url, metodo="POST",
                           headers={"Content-Type": ctype, "Origin": FRONT},
                           data=cuerpo)
        out.append({
            "caso": nombre, "status": res["status"], "ms": res["ms"],
            "cuerpo": (res["cuerpo"] or "")[:300],
            "contiene_traceback": "Traceback" in (res["cuerpo"] or ""),
            "contiene_sql_error": any(x in (res["cuerpo"] or "").lower()
                                      for x in ("syntax error", "sqlstate", "psycopg", "asyncpg")),
            "refleja_payload": "<script>alert(1)</script>" in (res["cuerpo"] or ""),
        })
    return out


def seccion_rate_limit():
    """Hasta 12 intentos de login fallidos; se corta antes si llega 429."""
    out = []
    for i in range(1, 13):
        res = peticion(
            f"{API}/api/auth/login", metodo="POST",
            headers={"Content-Type": "application/json", "Origin": FRONT},
            data=json.dumps({"email": "prueba-rate-limit@empresa.com", "password": "incorrecta"}),
        )
        out.append({"intento": i, "status": res["status"], "ms": res["ms"],
                    "cuerpo": (res["cuerpo"] or "")[:200],
                    "cabeceras_rate": {k: v for k, v in res["cabeceras"].items()
                                       if "rate" in k or "retry" in k or "limit" in k}})
        if res["status"] == 429:
            break
    return out


def seccion_info():
    raiz = peticion(f"{API}/")
    salud = peticion(f"{API}/api/health")
    return {
        "api_raiz": {"status": raiz["status"], "cuerpo": raiz["cuerpo"][:500]},
        "health": {"status": salud["status"], "cuerpo": salud["cuerpo"][:500]},
        "openapi": {"status": peticion(f"{API}/openapi.json")["status"],
                    "descripcion": "Especificación pública completa de la API"},
        "docs": {"status": peticion(f"{API}/docs")["status"],
                 "descripcion": "Swagger UI pública"},
        "redoc": {"status": peticion(f"{API}/redoc")["status"]},
    }


def main():
    informe = {
        "generado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "objetivos": {"frontend": FRONT, "apex": APEX, "api": API},
        "cabeceras": seccion_cabeceras(),
        "exposicion": seccion_exposicion(),
        "auth": seccion_auth(),
        "cors": seccion_cors(),
        "metodos": seccion_metodos(),
        "validacion": seccion_validacion(),
        "rate_limit": seccion_rate_limit(),
        "informacion": seccion_info(),
    }
    destino = DATOS / "recon.json"
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {destino}")
    print(f"  cabeceras: {len(informe['cabeceras'])} URLs")
    print(f"  exposicion: {len(informe['exposicion'])} rutas probadas")
    print(f"  auth: {len(informe['auth'])} endpoints")
    print(f"  rate-limit intentos: {len(informe['rate_limit'])} "
          f"(último status {informe['rate_limit'][-1]['status']})")


if __name__ == "__main__":
    main()
