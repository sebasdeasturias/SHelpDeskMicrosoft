"""Población de la BD con usuarios MOCK para el benchmark ISO/IEC 25000.

- 23 usuarios simulados repartidos en los 4 roles del sistema.
- Contraseña compartida: 'password123' (mismo hash bcrypt que seed_usuarios.sql).
- Idempotente: ON CONFLICT (email) DO NOTHING + UPDATE de estado/rol.
- Desbloqueo de cuentas y reset de contadores entre ejecuciones del benchmark.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Hash bcrypt de 'password123' (idéntico al de database/seed_usuarios.sql)
BCRYPT_PASSWORD123 = "$2b$12$iYqdmnOYc.sFE6TYLkdfIe80LhwpKH/VMRCbBtKBg6wcw7h/t/vvG"

PASSWORD = "password123"
DOMINIO = "bench.helpdesk.example.com"

# (rol, cantidad, área, especialidad, extras)
PLANTILLA = [
    ("solicitante", 12, "Ventas", None, {}),
    ("agente", 6, "Soporte TI", "Hardware y Redes", {"carga_trabajo": 0}),
    ("coordinador", 3, "Soporte TI", "Gestión de Equipos",
     {"nivel_jerarquia": 2, "permisos_supervision": True}),
    ("administrador", 2, "TI", "Administración de Sistemas",
     {"nivel_jerarquia": 3, "permisos_supervision": True, "permisos_especiales": True}),
]


def _env(*keys: str) -> dict[str, str]:
    env_file = ROOT / ".env"
    out = {}
    if env_file.exists():
        for linea in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in keys:
        if not out.get(k):
            raise RuntimeError(f"Variable {k} no encontrada en .env")
    return {k: out[k] for k in keys}


def _psql(sql: str, db: str | None = None) -> str:
    env = _env("POSTGRES_USER", "POSTGRES_DB")
    cmd = ["docker", "exec", "-i", "helpdesk-db", "psql", "-v", "ON_ERROR_STOP=1",
           "-U", env["POSTGRES_USER"], "-d", db or env["POSTGRES_DB"], "-tA"]
    proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"psql falló ({proc.returncode}): {proc.stderr.strip()[:500]}")
    return proc.stdout


def _sql_usuarios() -> str:
    filas = []
    for rol, cantidad, area, especialidad, extras in PLANTILLA:
        for i in range(1, cantidad + 1):
            email = f"bench.{rol}.{i:02d}@{DOMINIO}"
            nombre = f"Benchmark {rol.capitalize()} {i:02d}"
            esp = f"'{especialidad}'" if especialidad else "NULL"
            carga = extras.get("carga_trabajo", 0)
            jerarquia = extras.get("nivel_jerarquia")
            supervision = extras.get("permisos_supervision", False)
            acceso = extras.get("nivel_acceso")
            especiales = extras.get("permisos_especiales", False)
            filas.append(
                f"('{nombre}', '{email}', '{BCRYPT_PASSWORD123}', '{rol}', '{area}', "
                f"'activo', {esp}, {carga}, "
                f"{'NULL' if jerarquia is None else jerarquia}, "
                f"{'TRUE' if supervision else 'FALSE'}, "
                f"{'NULL' if acceso is not None else 'NULL'}, "
                f"{'TRUE' if especiales else 'FALSE'})"
            )
    values = ",\n".join(filas)
    return f"""
-- MOCK BENCHMARK ISO/IEC 25000: usuarios simulados (idempotente)
INSERT INTO usuarios (nombre, email, contraseña, rol, area, estado, especialidad,
                      carga_trabajo, nivel_jerarquia, permisos_supervision,
                      nivel_acceso, permisos_especiales)
VALUES
{values}
ON CONFLICT (email) DO UPDATE SET
    rol = EXCLUDED.rol,
    estado = 'activo',
    intentos_fallidos = 0,
    bloqueado_hasta = NULL;
"""


def _sql_reset() -> str:
    return f"""
-- Entre ejecuciones: desbloquear mocks, limpiar contadores y MFA residual
UPDATE usuarios
SET intentos_fallidos = 0, bloqueado_hasta = NULL, estado = 'activo',
    mfa_enabled = FALSE, mfa_secret = NULL
WHERE email LIKE '%@{DOMINIO}';
"""


def seed_mock_users() -> dict:
    """Crea/actualiza los usuarios mock y devuelve su inventario por rol."""
    # Migración de emails de dominios anteriores (p.ej. *.test, rechazados por EmailStr)
    _psql("""
        UPDATE usuarios
        SET email = replace(email, '@bench.helpdesk.test', '@""" + DOMINIO + """')
        WHERE email LIKE '%@bench.helpdesk.test';
    """)
    _psql(_sql_usuarios())
    _psql(_sql_reset())
    out = _psql(f"""
        SELECT id_usuario, nombre, email, rol FROM usuarios
        WHERE email LIKE '%@{DOMINIO}' ORDER BY rol, email;
    """)
    por_rol: dict[str, list[dict]] = {"solicitante": [], "agente": [],
                                      "coordinador": [], "administrador": []}
    for linea in out.strip().splitlines():
        if not linea.strip():
            continue
        id_u, nombre, email, rol = linea.split("|")[:4]
        por_rol.setdefault(rol, []).append(
            {"id": int(id_u), "nombre": nombre, "email": email, "rol": rol})
    total = sum(len(v) for v in por_rol.values())
    if total == 0:
        raise RuntimeError("No se creó ningún usuario mock")
    return {"password": PASSWORD, "por_rol": por_rol, "total": total}


def seed_corpus_tickets() -> int:
    """Aplica database/mock_tickets_resueltos.sql (60 tickets RAG) si falta."""
    archivo = ROOT / "database" / "mock_tickets_resueltos.sql"
    if not archivo.exists():
        return 0
    n_antes = _psql("SELECT count(*) FROM solicitud;").strip()
    _psql(archivo.read_text(encoding="utf-8"))
    n_despues = _psql("SELECT count(*) FROM solicitud;").strip()
    return max(int(n_despues or 0) - int(n_antes or 0), 0)


def estado_cuenta_mock(email: str) -> dict:
    out = _psql(f"""
        SELECT intentos_fallidos, bloqueado_hasta IS NOT NULL, token_version
        FROM usuarios WHERE email = '{email}';
    """).strip()
    if not out:
        return {"existe": False}
    intentos, bloqueado, tv = out.split("|")
    return {"existe": True, "intentos_fallidos": int(intentos),
            "bloqueado": bloqueado == "t", "token_version": int(tv)}


def desbloquear_todos_los_mocks() -> None:
    _psql(_sql_reset())
