# streamlit_app/backups.py
# Respaldos con pg_dump/pg_restore DIRECTOS contra Postgres (sin Docker exec).
# Los ficheros se escriben en el volumen compartido db_backups (/backups).
import os
import re
import subprocess
import time

DIR_BACKUPS = os.getenv("BACKUP_DIR", "/backups")
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+$")

PG_ENV = {
    **os.environ,
    "PGHOST": os.getenv("POSTGRES_HOST", "postgres"),
    "PGPORT": os.getenv("POSTGRES_PORT", "5432"),
    "PGUSER": os.getenv("POSTGRES_USER", ""),
    "PGPASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
    "PGDATABASE": os.getenv("POSTGRES_DB", ""),
}


def _run(cmd: list, timeout: int = 600):
    return subprocess.run(cmd, env=PG_ENV, capture_output=True, text=True, timeout=timeout)


def _validar(nombre: str) -> None:
    if not NOMBRE_VALIDO.match(nombre) or ".." in nombre:
        raise ValueError("Nombre de archivo inválido")


def crear_respaldo() -> str:
    """Crea un respaldo pg_dump -Fc con marca de tiempo. Devuelve el nombre del archivo."""
    nombre = f"helpdesk_{time.strftime('%Y%m%d_%H%M%S')}.dump"
    os.makedirs(DIR_BACKUPS, exist_ok=True)
    r = _run(["pg_dump", "-Fc", "-f", os.path.join(DIR_BACKUPS, nombre)])
    if r.returncode != 0:
        raise RuntimeError(f"pg_dump falló (exit {r.returncode}): {r.stderr[:300]}")
    return nombre


def listar_respaldos() -> list[dict]:
    """Lista los respaldos disponibles: nombre, tamaño (bytes) y fecha."""
    if not os.path.isdir(DIR_BACKUPS):
        return []
    respaldos = []
    for nombre in os.listdir(DIR_BACKUPS):
        if not nombre.endswith(".dump"):
            continue
        st = os.stat(os.path.join(DIR_BACKUPS, nombre))
        respaldos.append({
            "nombre": nombre,
            "bytes": st.st_size,
            "fecha": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        })
    return sorted(respaldos, key=lambda r: r["nombre"], reverse=True)


def descargar_respaldo(nombre: str) -> bytes:
    """Devuelve el contenido binario de un respaldo para su descarga."""
    _validar(nombre)
    with open(os.path.join(DIR_BACKUPS, nombre), "rb") as f:
        return f.read()


def eliminar_respaldo(nombre: str) -> None:
    """Elimina un respaldo del volumen (nombre validado contra path traversal)."""
    _validar(nombre)
    os.remove(os.path.join(DIR_BACKUPS, nombre))


def restaurar_respaldo(nombre: str) -> None:
    """Restaura un respaldo (pg_restore) — PELIGROSO: sobreescribe la BD actual."""
    _validar(nombre)
    r = _run(["pg_restore", "-d", PG_ENV["PGDATABASE"], "--clean", "--if-exists",
              os.path.join(DIR_BACKUPS, nombre)])
    if r.returncode != 0:
        raise RuntimeError(f"pg_restore falló (exit {r.returncode}): {r.stderr[:300]}")
