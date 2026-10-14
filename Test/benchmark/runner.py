"""Motor de benchmark por módulos del HelpDesk (familia ISO/IEC 25000).

Ejecuta escenarios HTTP reales contra el stack levantado con iniciar.sh,
usando los usuarios mock (Test/benchmark/mocks.py), y mide las métricas de
ISO/IEC 25023 (tiempo de respuesta, rendimiento, tasa de error, disponibilidad)
por cada módulo del sistema:

    infraestructura, auth, tickets, adjuntos, chat_global, chat_privado,
    chat_ia, coordinador, seguridad (rate-limit/autorización), base_datos,
    auditoria, streamlit, frontend, ia_externa (ollama/n8n)

Solo usa la stdlib + `requests` (disponible en el host).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import math
import os
import re
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parents[2]

API = os.environ.get("BENCH_API", "http://127.0.0.1:8000")
STREAMLIT = os.environ.get("BENCH_STREAMLIT", "http://127.0.0.1:8501")
OLLAMA = os.environ.get("BENCH_OLLAMA", "http://127.0.0.1:11434")
N8N = os.environ.get("BENCH_N8N", "http://127.0.0.1:5678")

_tls = threading.local()


def _session() -> requests.Session:
    if not hasattr(_tls, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": "SHelpDesk-ISO25000-Benchmark/1.0"})
        _tls.s = s
    return _tls.s


# ---------------------------------------------------------------------------
# Estadística de latencia (ISO/IEC 25023 — time behavior)
# ---------------------------------------------------------------------------
def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def latencia(vals: list[float]) -> dict[str, float]:
    v = sorted(vals)
    if not v:
        return {"n": 0}
    return {
        "n": len(v),
        "min_ms": round(v[0], 2),
        "p50_ms": round(_pct(v, 0.50), 2),
        "p90_ms": round(_pct(v, 0.90), 2),
        "p95_ms": round(_pct(v, 0.95), 2),
        "p99_ms": round(_pct(v, 0.99), 2),
        "max_ms": round(v[-1], 2),
        "mean_ms": round(statistics.fmean(v), 2),
        "stdev_ms": round(statistics.pstdev(v), 2) if len(v) > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Escenarios genéricos HTTP
# ---------------------------------------------------------------------------
@dataclass
class Escenario:
    modulo: str
    nombre: str
    metodo: str
    path: str                       # relativo a API o URL absoluta
    esperado: tuple[int, ...] = (200,)
    json_body: Any = None
    files: Any = None               # (nombre_archivo, bytes, content_type)
    token: str | None = None
    rol_token: str | None = None    # para elegir token del pool por rol
    concurrencia: int = 4
    iteraciones: int = 20
    extras: dict = field(default_factory=dict)


def _url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{API}{path}"


def ejecutar_escenario(esc: Escenario, tokens: dict[str, str],
                       emails: dict[str, list[str]]) -> dict:
    """Ejecuta un escenario con concurrencia; devuelve métricas agregadas."""
    lat: list[float] = []
    status_counts: dict[str, int] = {}
    errores: list[str] = []
    lock = threading.Lock()
    token_iter_holder = {"i": 0}

    def _token_para(i: int) -> str | None:
        if esc.token:
            return esc.token
        if esc.rol_token:
            pool = emails.get(esc.rol_token, [])
            if pool:
                # rota el email (respeta rate-limits por cuenta)
                email = pool[token_iter_holder["i"] % len(pool)]
                token_iter_holder["i"] += 1
                return tokens.get(email)
        return None

    def _una(i: int) -> None:
        tok = _token_para(i)
        headers = {"Authorization": f"Bearer {tok}"} if tok else {}
        t0 = time.perf_counter()
        try:
            kw: dict = {"timeout": 30}
            if esc.json_body is not None and esc.files is None:
                kw["json"] = esc.json_body
            if esc.files is not None:
                nombre, data, ctype = esc.files
                if callable(data):
                    data = data()
                kw["files"] = {"files": (nombre, data, ctype)}
            r = _session().request(esc.metodo, _url(esc.path), headers=headers, **kw)
            dt = (time.perf_counter() - t0) * 1000
            with lock:
                lat.append(dt)
                clave = str(r.status_code)
                status_counts[clave] = status_counts.get(clave, 0) + 1
                if r.status_code not in esc.esperado and len(errores) < 5:
                    errores.append(f"HTTP {r.status_code}: {r.text[:160]}")
        except Exception as exc:  # red/timeout
            dt = (time.perf_counter() - t0) * 1000
            with lock:
                lat.append(dt)
                status_counts["EXCEPCION"] = status_counts.get("EXCEPCION", 0) + 1
                if len(errores) < 5:
                    errores.append(f"{type(exc).__name__}: {exc}")

    t_wall0 = time.perf_counter()
    con = max(1, esc.concurrencia)
    with cf.ThreadPoolExecutor(max_workers=con) as ex:
        list(ex.map(_una, range(esc.iteraciones)))
    wall = time.perf_counter() - t_wall0

    ok = sum(status_counts.get(str(c), 0) for c in esc.esperado)
    total = sum(status_counts.values()) or 1
    return {
        "modulo": esc.modulo,
        "escenario": esc.nombre,
        "metodo": esc.metodo,
        "path": esc.path,
        "esperado": list(esc.esperado),
        "status_counts": status_counts,
        "muestreo": esc.iteraciones,
        "concurrencia": con,
        "ok": ok,
        "errores": errores,
        "tasa_ok": round(ok / total, 4),
        "tasa_error": round(1 - ok / total, 4),
        "duracion_s": round(wall, 3),
        "throughput_rps": round(total / wall, 2) if wall > 0 else 0.0,
        "latencia": latencia(lat),
        **({"extras": esc.extras} if esc.extras else {}),
    }


# ---------------------------------------------------------------------------
# Probes especiales (no HTTP genérico)
# ---------------------------------------------------------------------------
def _psql(sql: str) -> str:
    env = {}
    for linea in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    cmd = ["docker", "exec", "-i", "helpdesk-db", "psql", "-v", "ON_ERROR_STOP=1",
           "-U", env.get("POSTGRES_USER", "postgres"),
           "-d", env.get("POSTGRES_DB", "helpdesk_db"), "-tA"]
    proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300])
    return proc.stdout


def probe_base_datos(iteraciones: int = 15) -> dict:
    """Latencia real de consultas SQL representativas del sistema (ISO/IEC 25023)."""
    consultas = {
        "count_solicitudes": "SELECT count(*) FROM solicitud;",
        "listado_tickets_joins": """
            SELECT s.id_solicitud, s.asunto, s.estado, u.nombre, c.nombre, p.nivel
            FROM solicitud s
            LEFT JOIN usuarios u ON s.id_agente_asignado = u.id_usuario
            LEFT JOIN categoria c ON s.id_categoria = c.id_categoria
            LEFT JOIN prioridad p ON s.id_prioridad = p.id_prioridad
            WHERE s.estado != 'archivado'
            ORDER BY s.fecha_creacion DESC LIMIT 100;""",
        "kpi_sla": """
            SELECT count(*) FILTER (WHERE s.estado IN ('resuelto','cerrado')) AS resueltos,
                   count(*) FILTER (WHERE s.estado = 'en_proceso') AS en_proceso
            FROM solicitud s;""",
        "historial_por_ticket": """
            SELECT h.* FROM historial h JOIN solicitud s USING (id_solicitud)
            ORDER BY h.fecha DESC LIMIT 200;""",
        "insert_log_bench": f"INSERT INTO log (accion, detalles) VALUES ('benchmark_iso25000', 'psql timing {time.time():.0f}');",
    }
    out = {}
    for nombre, sql in consultas.items():
        lat = []
        fallos = 0
        for _ in range(iteraciones if nombre != "insert_log_bench" else 5):
            t0 = time.perf_counter()
            try:
                _psql(sql)
                if nombre != "insert_log_bench":
                    _psql("SELECT 1;")  # commit implícito ya hecho vía psql autocommit
                lat.append((time.perf_counter() - t0) * 1000)
            except Exception:
                fallos += 1
        out[nombre] = {"latencia": latencia(lat), "fallos": fallos}
    return {"consultas": out, "nota": "Medido con psql sobre el contenedor helpdesk-db (incluye overhead del shell/docker exec)."}


def probe_auditoria() -> dict:
    """Verificaciones de integridad de auditoría (histórico/log) — ISO/IEC 25012."""
    checks = {
        "historial_huerfanos": """
            SELECT count(*) FROM historial h
            LEFT JOIN solicitud s ON s.id_solicitud = h.id_solicitud
            WHERE s.id_solicitud IS NULL;""",
        "historial_estados_invalidos": """
            SELECT count(*) FROM historial
            WHERE estado_nuevo NOT IN ('nuevo','asignado','en_proceso','resuelto','cerrado','escalado','archivado');""",
        "solicitud_estados_invalidos": """
            SELECT count(*) FROM solicitud
            WHERE estado NOT IN ('nuevo','asignado','en_proceso','resuelto','cerrado','escalado','archivado');""",
        "fechas_inconsistentes": """
            SELECT count(*) FROM solicitud
            WHERE fecha_actualizacion IS NOT NULL AND fecha_creacion IS NOT NULL
              AND fecha_actualizacion < fecha_creacion;""",
        "usuarios_password_vacia": """
            SELECT count(*) FROM usuarios WHERE contraseña IS NULL OR length(contraseña) < 20;""",
        "log_benchmark_registrado": """
            SELECT count(*) FROM log WHERE accion LIKE 'login%' OR accion LIKE 'benchmark%';""",
        "historial_total": "SELECT count(*) FROM historial;",
        "log_total": "SELECT count(*) FROM log;",
    }
    res = {}
    for nombre, sql in checks.items():
        try:
            res[nombre] = int(_psql(sql).strip() or 0)
        except Exception as exc:
            res[nombre] = f"error: {exc}"
    return res


def probe_seguridad_auth(tokens: dict[str, str], emails: dict[str, list[str]]) -> dict:
    """Controles de seguridad: rate-limit de login, lockout, JWT, RBAC."""
    res: dict[str, Any] = {}

    # 1) Token inválido → 401
    r = _session().get(f"{API}/api/auth/me",
                       headers={"Authorization": "Bearer token-falso-iso25000"},
                       timeout=15)
    res["jwt_invalido_401"] = r.status_code == 401

    # 2) Sin token → 401/403
    r = _session().get(f"{API}/api/auth/me", timeout=15)
    res["sin_token_rechazado"] = r.status_code in (401, 403)

    # 3) RBAC: solicitante no puede ver estadísticas de coordinador
    tok_sol = tokens.get(emails["solicitante"][0])
    r = _session().get(f"{API}/api/coordinator/estadisticas",
                       headers={"Authorization": f"Bearer {tok_sol}"}, timeout=15)
    res["rbac_solicitante_bloqueado"] = r.status_code in (401, 403)

    # 4) RBAC: solicitante no puede crear chat con IA
    r = _session().post(f"{API}/api/chat",
                        headers={"Authorization": f"Bearer {tok_sol}"},
                        json={"mensaje": "intento benchmark"}, timeout=15)
    res["rbac_chat_ia_solo_staff"] = r.status_code == 403

    # 5) Login con contraseña incorrecta (registro + bloqueo por cuenta)
    victima = emails["solicitante"][-1]
    statuses = []
    for _ in range(6):
        r = _session().post(f"{API}/api/auth/login",
                            json={"email": victima, "password": "clave-mala-iso25000"},
                            timeout=15)
        statuses.append(r.status_code)
    res["login_malo_status"] = statuses
    res["lockout_tras_5_fallos"] = any(s == 429 for s in statuses)

    # 6) El endpoint de tickets exige token (BUG #2 ya corregido en el código)
    r = _session().get(f"{API}/api/tickets", timeout=15)
    res["tickets_sin_token_401"] = r.status_code in (401, 403)

    # limpiar: desbloquear la víctima para el resto del run
    from .mocks import desbloquear_todos_los_mocks
    desbloquear_todos_los_mocks()
    return res


def probe_infraestructura() -> dict:
    """Estado real de los contenedores + health completo del backend."""
    out: dict[str, Any] = {"containers": {}}
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=20)
        for linea in proc.stdout.splitlines():
            if linea.lower().startswith(("helpdesk", "n8n", "ollama")):
                nombre, estado = linea.split("\t", 1)
                out["containers"][nombre] = estado
    except Exception as exc:
        out["containers_error"] = str(exc)
    try:
        r = _session().get(f"{API}/api/health", timeout=10)
        out["health_status_code"] = r.status_code
        out["health_body"] = r.json()
    except Exception as exc:
        out["health_error"] = str(exc)
    return out


def probe_frontend() -> dict:
    """Calidad del frontend estático (peso, estructura) — ISO/IEC 25010."""
    fe = ROOT / "frontend"
    assets = []
    for ext in ("*.html", "*.js", "*.css"):
        for p in fe.rglob(ext):
            assets.append({"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size})
    htmls = [p for p in fe.rglob("*.html")]
    js_handlers = 0
    inline_scripts = 0
    for p in htmls:
        src = p.read_text(encoding="utf-8", errors="ignore")
        js_handlers += len(re.findall(r"\son[a-z]+=", src))
        inline_scripts += len(re.findall(r"<script(?![^>]*\bsrc=)", src))
    total = sum(a["bytes"] for a in assets)
    return {
        "archivos": len(assets),
        "peso_total_bytes": total,
        "peso_total_kb": round(total / 1024, 1),
        "mayor_archivo": max(assets, key=lambda a: a["bytes"]) if assets else None,
        "paginas_html": len(htmls),
        "handlers_inline": js_handlers,
        "scripts_inline": inline_scripts,
    }


def probe_ia_externa() -> dict:
    """Disponibilidad/latencia de Ollama y n8n (dependencias IA)."""
    out = {}
    for nombre, url in (("ollama", f"{OLLAMA}/api/tags"),
                        ("n8n", f"{N8N}/healthz"),
                        ("backend_chat_health", f"{API}/api/chat/health")):
        try:
            t0 = time.perf_counter()
            r = _session().get(url, timeout=8)
            out[nombre] = {
                "status_code": r.status_code,
                "latencia_ms": round((time.perf_counter() - t0) * 1000, 2),
                "disponible": r.status_code == 200,
            }
        except Exception as exc:
            out[nombre] = {"disponible": False, "error": f"{type(exc).__name__}"}
    return out


# ---------------------------------------------------------------------------
# Orquestador de módulos
# ---------------------------------------------------------------------------
def login_pool(inventario: dict) -> tuple[dict[str, str], dict[str, list[str]], list[dict]]:
    """Login único por usuario mock; devuelve tokens y emails por rol."""
    tokens: dict[str, str] = {}
    emails: dict[str, list[str]] = {}
    logins: list[dict] = []
    for rol, usuarios in inventario["por_rol"].items():
        emails[rol] = [u["email"] for u in usuarios]
        for u in usuarios:
            t0 = time.perf_counter()
            try:
                r = _session().post(f"{API}/api/auth/login",
                                    json={"email": u["email"],
                                          "password": inventario["password"]},
                                    timeout=20)
                dt = (time.perf_counter() - t0) * 1000
                body = r.json() if r.ok else {}
                if r.ok and body.get("access_token"):
                    tokens[u["email"]] = body["access_token"]
                logins.append({"email": u["email"], "rol": rol,
                               "status": r.status_code, "ms": round(dt, 2)})
            except Exception as exc:
                logins.append({"email": u["email"], "rol": rol, "error": str(exc)})
    return tokens, emails, logins


def _png_bytes(n: int) -> bytes:
    """PNG mínimo válido (1x1) con padding para alcanzar ~n bytes."""
    base = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c626001000000ffff03000006000557bfabd4000000"
        "0049454e44ae426082")
    if n <= len(base):
        return base
    return base[:-12] + b"\x00" * (n - len(base)) + base[-12:]


def construir_escenarios(emails: dict[str, list[str]]) -> list[Escenario]:
    esc: list[Escenario] = []

    # --- infraestructura ---
    esc += [
        Escenario("infraestructura", "health_backend", "GET", "/api/health",
                  esperado=(200, 503), concurrencia=4, iteraciones=12),
        Escenario("infraestructura", "raiz_api", "GET", "/",
                  concurrencia=4, iteraciones=10),
    ]

    # --- auth ---
    esc += [
        Escenario("auth", "login_mock_rotando", "POST", "/api/auth/login",
                  json_body=None, esperado=(200,),  # el body se inyecta abajo
                  concurrencia=3, iteraciones=24),
        Escenario("auth", "whoami_me", "GET", "/api/auth/me",
                  rol_token="coordinador", concurrencia=6, iteraciones=40),
        Escenario("auth", "me_solicitante", "GET", "/api/auth/me",
                  rol_token="solicitante", concurrencia=6, iteraciones=30),
    ]

    # --- tickets ---
    esc += [
        Escenario("tickets", "listado_coordinador", "GET", "/api/tickets",
                  rol_token="coordinador", concurrencia=8, iteraciones=40),
        Escenario("tickets", "listado_solicitante", "GET", "/api/tickets",
                  rol_token="solicitante", concurrencia=8, iteraciones=40),
        Escenario("tickets", "listado_agente", "GET", "/api/tickets",
                  rol_token="agente", concurrencia=6, iteraciones=30),
        Escenario("tickets", "crear_ticket_solicitante", "POST", "/api/tickets",
                  esperado=(201,), rol_token="solicitante",
                  concurrencia=3, iteraciones=18),
    ]

    # --- adjuntos ---
    esc += [
        Escenario("adjuntos", "subir_png_128kb", "POST",
                  "/api/tickets/1/adjuntos", esperado=(201,),
                  rol_token="solicitante", concurrencia=2, iteraciones=6,
                  files=("bench_iso25000.png", lambda: _png_bytes(128 * 1024),
                         "image/png")),
        Escenario("adjuntos", "listar_adjuntos", "GET",
                  "/api/tickets/1/adjuntos", rol_token="coordinador",
                  concurrencia=4, iteraciones=20),
    ]

    # --- chat global ---
    esc += [
        Escenario("chat_global", "historial", "GET",
                  "/api/chat-global/mensajes?limit=50",
                  rol_token="agente", concurrencia=8, iteraciones=40),
        Escenario("chat_global", "enviar_mensaje", "POST",
                  "/api/chat-global/mensajes", esperado=(201,),
                  json_body={"mensaje": "Benchmark ISO/IEC 25000 — mensaje de prueba"},
                  rol_token="agente", concurrencia=4, iteraciones=24),
    ]

    # --- chat privado ---
    esc += [
        Escenario("chat_privado", "contactos", "GET",
                  "/api/chat-privado/contactos", rol_token="agente",
                  concurrencia=6, iteraciones=30),
        Escenario("chat_privado", "no_leidos", "GET",
                  "/api/chat-privado/no-leidos", rol_token="coordinador",
                  concurrencia=6, iteraciones=30),
    ]

    # --- chat IA ---
    esc += [
        Escenario("chat_ia", "health_n8n", "GET", "/api/chat/health",
                  concurrencia=2, iteraciones=8),
        # 1 mensaje por usuario staff (cooldown 3 s/usuario, 30/min)
        Escenario("chat_ia", "mensaje_ia", "POST", "/api/chat",
                  esperado=(200, 429, 502, 503, 504),
                  json_body={"mensaje": "¿Cuántos tickets hay abiertos? (benchmark)"},
                  rol_token="agente", concurrencia=1, iteraciones=5),
    ]

    # --- coordinador ---
    for nombre, path in (
        ("estadisticas", "/api/coordinator/estadisticas"),
        ("reportes", "/api/coordinator/reportes"),
        ("agentes", "/api/coordinator/agentes"),
        ("asignacion", "/api/coordinator/asignacion"),
        ("sla", "/api/coordinator/sla"),
        # endpoints exclusivos del administrador
        ("usuarios", "/api/coordinator/usuarios"),
        ("bd_tablas", "/api/coordinator/bd/tablas"),
        ("ia_config", "/api/coordinator/ia"),
        ("n8n_workflows", "/api/coordinator/n8n/workflows"),
    ):
        rol = ("administrador" if nombre in
               ("usuarios", "bd_tablas", "ia_config", "n8n_workflows")
               else "coordinador")
        esc.append(Escenario("coordinador", nombre, "GET", path,
                             rol_token=rol, concurrencia=4, iteraciones=12))

    # asignación real de un ticket (escritura controlada)
    esc.append(Escenario("coordinador", "asignar_ticket", "POST",
                         "/api/coordinator/asignar/1", esperado=(200, 400),
                         json_body=None, rol_token="coordinador",
                         concurrencia=1, iteraciones=3))

    # --- streamlit ---
    esc.append(Escenario("streamlit", "panel_admin", "GET", f"{STREAMLIT}/",
                         concurrencia=3, iteraciones=10))

    return esc


def run_all(inventario: dict) -> dict:
    """Ejecuta el benchmark completo y devuelve los resultados crudos."""
    tokens, emails, logins = login_pool(inventario)
    escenarios = construir_escenarios(emails)

    # inyectar bodies dinámicos
    sol_pool = list(emails.get("solicitante", []))
    resultados_login: list[dict] = []
    agentes = [u["id"] for u in inventario["por_rol"]["agente"]]

    for esc in escenarios:
        if esc.nombre == "login_mock_rotando":
            esc.json_body = {"email": sol_pool[0],
                             "password": inventario["password"]}
        if esc.nombre == "crear_ticket_solicitante":
            esc.json_body = None  # se compone en el worker con id de solicitante
        if esc.nombre == "asignar_ticket":
            esc.json_body = {"agente_id": agentes[0] if agentes else None}

    # Escenario especial de login rotando emails (respeta 5 logins/email/15 min)
    def _ejecutar_login_rotando() -> dict:
        lat, status_counts, errores = [], {}, []
        pool = emails.get("solicitante", []) + emails.get("agente", [])
        for i in range(24):
            email = pool[i % len(pool)]
            t0 = time.perf_counter()
            try:
                r = _session().post(f"{API}/api/auth/login",
                                    json={"email": email,
                                          "password": inventario["password"]},
                                    timeout=20)
                lat.append((time.perf_counter() - t0) * 1000)
                k = str(r.status_code)
                status_counts[k] = status_counts.get(k, 0) + 1
                if r.status_code != 200 and len(errores) < 5:
                    errores.append(f"HTTP {r.status_code}: {r.text[:120]}")
            except Exception as exc:
                lat.append((time.perf_counter() - t0) * 1000)
                status_counts["EXCEPCION"] = status_counts.get("EXCEPCION", 0) + 1
                if len(errores) < 5:
                    errores.append(str(exc))
        ok = status_counts.get("200", 0)
        return {
            "modulo": "auth", "escenario": "login_mock_rotando",
            "metodo": "POST", "path": "/api/auth/login",
            "esperado": [200], "status_counts": status_counts,
            "muestreo": 24, "concurrencia": 1, "ok": ok, "errores": errores,
            "tasa_ok": round(ok / 24, 4), "tasa_error": round(1 - ok / 24, 4),
            "duracion_s": 0, "throughput_rps": 0,
            "latencia": latencia(lat),
        }

    # Escenario especial de creación de tickets (1 por solicitante, ≤3 c/u)
    def _ejecutar_crear_tickets() -> dict:
        lat, status_counts, errores, creados = [], {}, [], []
        idx = 0
        for _ in range(18):
            email = sol_pool[idx % len(sol_pool)]
            idx += 1
            tok = tokens.get(email)
            body = {"asunto": f"Benchmark ISO25000 #{idx}",
                    "descripcion": "Ticket generado por la suite de benchmark "
                                   "para medir el módulo de tickets.",
                    "id_categoria": 2, "id_prioridad": 3}
            t0 = time.perf_counter()
            try:
                r = _session().post(f"{API}/api/tickets", json=body,
                                    headers={"Authorization": f"Bearer {tok}"},
                                    timeout=20)
                lat.append((time.perf_counter() - t0) * 1000)
                k = str(r.status_code)
                status_counts[k] = status_counts.get(k, 0) + 1
                if r.ok:
                    creados.append(r.json().get("ticket_id"))
                elif len(errores) < 5:
                    errores.append(f"HTTP {r.status_code}: {r.text[:120]}")
            except Exception as exc:
                lat.append((time.perf_counter() - t0) * 1000)
                status_counts["EXCEPCION"] = status_counts.get("EXCEPCION", 0) + 1
                if len(errores) < 5:
                    errores.append(str(exc))
        ok = status_counts.get("201", 0)
        return {
            "modulo": "tickets", "escenario": "crear_ticket_solicitante",
            "metodo": "POST", "path": "/api/tickets",
            "esperado": [201], "status_counts": status_counts,
            "muestreo": 18, "concurrencia": 1, "ok": ok, "errores": errores,
            "tasa_ok": round(ok / 18, 4), "tasa_error": round(1 - ok / 18, 4),
            "duracion_s": 0, "throughput_rps": 0,
            "latencia": latencia(lat),
            "tickets_creados": [t for t in creados if t],
        }

    # Escenario especial chat IA (cooldown 3 s ⇒ secuencial con espera)
    def _ejecutar_chat_ia() -> dict:
        lat, status_counts, errores = [], {}, []
        staff = (emails.get("coordinador", []) + emails.get("administrador", [])
                 + emails.get("agente", []))
        for i, email in enumerate(staff[:6]):
            tok = tokens.get(email)
            t0 = time.perf_counter()
            try:
                r = _session().post(f"{API}/api/chat",
                                    json={"mensaje": "Resumen de tickets activos (benchmark ISO 25000)"},
                                    headers={"Authorization": f"Bearer {tok}"},
                                    timeout=60)
                lat.append((time.perf_counter() - t0) * 1000)
                k = str(r.status_code)
                status_counts[k] = status_counts.get(k, 0) + 1
                if r.status_code not in (200, 429) and len(errores) < 5:
                    errores.append(f"HTTP {r.status_code}: {r.text[:120]}")
            except Exception as exc:
                lat.append((time.perf_counter() - t0) * 1000)
                status_counts["EXCEPCION"] = status_counts.get("EXCEPCION", 0) + 1
                if len(errores) < 5:
                    errores.append(str(exc))
            time.sleep(3.2)  # respeta el cooldown de 3 s del backend
        ok = sum(status_counts.get(str(c), 0) for c in (200, 429))
        n = max(len(staff[:6]), 1)
        return {
            "modulo": "chat_ia", "escenario": "mensaje_ia",
            "metodo": "POST", "path": "/api/chat",
            "esperado": [200, 429], "status_counts": status_counts,
            "muestreo": n, "concurrencia": 1, "ok": ok, "errores": errores,
            "tasa_ok": round(ok / n, 4), "tasa_error": round(1 - ok / n, 4),
            "duracion_s": 0, "throughput_rps": 0,
            "latencia": latencia(lat),
        }

    def _ejecutar_subir_adjuntos(esc: Escenario) -> dict:
        # ticket del primer solicitante mock; limpia adjuntos previos del bench
        # (el backend limita a 5 adjuntos por ticket)
        out = _psql(f"""
            SELECT s.id_solicitud FROM solicitud s
            JOIN usuarios u ON u.id_usuario = s.id_solicitante
            WHERE u.email = '{sol_pool[0]}' ORDER BY s.id_solicitud DESC LIMIT 1;
        """).strip()
        tid = int(out) if out else 1
        _psql(f"DELETE FROM adjunto WHERE id_solicitud = {tid};")
        esc_mod = Escenario(
            modulo=esc.modulo, nombre=esc.nombre, metodo="POST",
            path=f"/api/tickets/{tid}/adjuntos", esperado=esc.esperado,
            token=tokens.get(sol_pool[0]), concurrencia=1,
            iteraciones=5, files=esc.files)
        return ejecutar_escenario(esc_mod, tokens, emails)

    def _ejecutar_listar_adjuntos(esc: Escenario) -> dict:
        # resuelve un ticket existente (no hardcodea id=1)
        out = _psql("""
            SELECT id_solicitud FROM solicitud ORDER BY id_solicitud DESC LIMIT 1;
        """).strip()
        tid = int(out) if out else 1
        esc_mod = Escenario(
            modulo=esc.modulo, nombre=esc.nombre, metodo="GET",
            path=f"/api/tickets/{tid}/adjuntos", esperado=esc.esperado,
            rol_token=esc.rol_token, concurrencia=esc.concurrencia,
            iteraciones=esc.iteraciones)
        return ejecutar_escenario(esc_mod, tokens, emails)

    def _ejecutar_asignar(esc: Escenario) -> dict:
        # 3 asignaciones sobre tickets 'nuevo' distintos (o 1 si no hay más)
        lat, status_counts, errores = [], {}, []
        nuevos = _psql("""
            SELECT id_solicitud FROM solicitud WHERE estado = 'nuevo'
            ORDER BY id_solicitud LIMIT 3;
        """).strip().splitlines()
        tok = tokens.get(emails["coordinador"][0])
        for i, nid in enumerate(nuevos or ["1"]):
            body = {"agente_id": agentes[i % len(agentes)]}
            t0 = time.perf_counter()
            try:
                r = _session().post(f"{API}/api/coordinator/asignar/{nid.strip()}",
                                    json=body,
                                    headers={"Authorization": f"Bearer {tok}"},
                                    timeout=20)
                lat.append((time.perf_counter() - t0) * 1000)
                k = str(r.status_code)
                status_counts[k] = status_counts.get(k, 0) + 1
                if r.status_code not in (200, 400) and len(errores) < 5:
                    errores.append(f"HTTP {r.status_code}: {r.text[:120]}")
            except Exception as exc:
                lat.append((time.perf_counter() - t0) * 1000)
                status_counts["EXCEPCION"] = status_counts.get("EXCEPCION", 0) + 1
                errores.append(str(exc))
        n = max(len(nuevos), 1)
        ok = sum(status_counts.get(str(c), 0) for c in (200, 400))
        return {
            "modulo": "coordinador", "escenario": "asignar_ticket",
            "metodo": "POST", "path": "/api/coordinator/asignar/{id}",
            "esperado": [200, 400], "status_counts": status_counts,
            "muestreo": n, "concurrencia": 1, "ok": ok, "errores": errores,
            "tasa_ok": round(ok / n, 4), "tasa_error": round(1 - ok / n, 4),
            "duracion_s": 0, "throughput_rps": 0,
            "latencia": latencia(lat),
        }

    especiales = {
        "login_mock_rotando": _ejecutar_login_rotando,
        "crear_ticket_solicitante": _ejecutar_crear_tickets,
        "mensaje_ia": _ejecutar_chat_ia,
        "subir_png_128kb": lambda: _ejecutar_subir_adjuntos(
            next(e for e in escenarios if e.nombre == "subir_png_128kb")),
        "listar_adjuntos": lambda: _ejecutar_listar_adjuntos(
            next(e for e in escenarios if e.nombre == "listar_adjuntos")),
        "asignar_ticket": lambda: _ejecutar_asignar(
            next(e for e in escenarios if e.nombre == "asignar_ticket")),
    }

    escenarios_http = [e for e in escenarios if e.nombre not in especiales]

    resultados: dict[str, list[dict]] = {}
    print(f"[bench] {len(escenarios_http)} escenarios HTTP + "
          f"{len(especiales)} especiales + probes...")
    for esc in escenarios_http:
        r = ejecutar_escenario(esc, tokens, emails)
        resultados.setdefault(esc.modulo, []).append(r)
        lat = r["latencia"]
        print(f"  [{esc.modulo:<13}] {esc.nombre:<26} ok={r['tasa_ok']:.0%} "
              f"p95={lat.get('p95_ms', 0):>7.1f}ms")

    for nombre, fn in especiales.items():
        try:
            r = fn()
            resultados.setdefault(r["modulo"], []).append(r)
            lat = r["latencia"]
            print(f"  [{r['modulo']:<13}] {nombre:<26} ok={r['tasa_ok']:.0%} "
                  f"p95={lat.get('p95_ms', 0):>7.1f}ms")
        except Exception as exc:
            resultados.setdefault("errores", []).append(
                {"escenario": nombre, "error": str(exc)})
            print(f"  [ERROR] {nombre}: {exc}")

    print("[bench] probes: seguridad, BD, auditoría, infra, frontend, IA...")
    custom = {}
    try:
        custom["seguridad_auth"] = probe_seguridad_auth(tokens, emails)
    except Exception as exc:
        custom["seguridad_auth"] = {"error": str(exc)}
    try:
        custom["base_datos"] = probe_base_datos()
    except Exception as exc:
        custom["base_datos"] = {"error": str(exc)}
    try:
        custom["auditoria"] = probe_auditoria()
    except Exception as exc:
        custom["auditoria"] = {"error": str(exc)}
    try:
        custom["infraestructura"] = probe_infraestructura()
    except Exception as exc:
        custom["infraestructura"] = {"error": str(exc)}
    try:
        custom["frontend"] = probe_frontend()
    except Exception as exc:
        custom["frontend"] = {"error": str(exc)}
    try:
        custom["ia_externa"] = probe_ia_externa()
    except Exception as exc:
        custom["ia_externa"] = {"error": str(exc)}

    return {
        "logins_setup": logins,
        "tokens_emitidos": len(tokens),
        "usuarios_mock": inventario["total"],
        "escenarios": resultados,
        "custom": custom,
    }
