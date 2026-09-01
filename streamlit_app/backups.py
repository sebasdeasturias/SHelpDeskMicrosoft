# streamlit_app/backups.py
# Respaldos de la base de datos: se ejecutan con pg_dump dentro del contenedor
# helpdesk-db (volumen db_backups montado en /backups) vía Docker Engine API.
import re
import docker_api

CONTENEDOR_BD = "helpdesk-db"
DIR_BACKUPS = "/backups"
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+$")


def _comando(comando: list) -> tuple[int, str, bytes]:
    """Helper: ejecuta y devuelve (exit_code, texto_salida, bytes_stdout)."""
    code, out, err = docker_api.container_exec(CONTENEDOR_BD, comando)
    return code, out.decode("utf-8", errors="replace"), out


def crear_respaldo() -> str:
    """Crea un respaldo pg_dump -Fc con marca de tiempo. Devuelve el nombre del archivo."""
    import time as _t
    nombre = f"helpdesk_{_t.strftime('%Y%m%d_%H%M%S')}.dump"
    code, out, _ = _comando([
        "sh", "-c",
        f"pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f {DIR_BACKUPS}/{nombre}"
    ])
    if code != 0:
        raise RuntimeError(f"pg_dump falló (exit {code})")
    return nombre


def listar_respaldos() -> list[dict]:
    """Lista los respaldos disponibles: nombre, tamaño (bytes) y fecha."""
    code, out, _ = _comando(["sh", "-c", f"ls -la --time-style='+%Y-%m-%d %H:%M' {DIR_BACKUPS}"])
    if code != 0:
        raise RuntimeError("No se pudo listar /backups (¿volumen montado?)")
    respaldos = []
    for linea in out.splitlines():
        partes = linea.split()
        if len(partes) < 8 or not partes[-1].endswith(".dump"):
            continue
        respaldos.append({
            "nombre": partes[-1],
            "bytes": int(partes[4]),
            "fecha": f"{partes[5]} {partes[6]}",
        })
    return sorted(respaldos, key=lambda r: r["nombre"], reverse=True)


def descargar_respaldo(nombre: str) -> bytes:
    """Devuelve el contenido binario de un respaldo para su descarga."""
    if not NOMBRE_VALIDO.match(nombre) or ".." in nombre:
        raise ValueError("Nombre de archivo inválido")
    code, out, _ = _comando(["sh", "-c", f"cat {DIR_BACKUPS}/{nombre}"])
    if code != 0:
        raise RuntimeError("No se pudo leer el respaldo")
    return out


def eliminar_respaldo(nombre: str) -> None:
    """Elimina un respaldo del volumen (nombre validado contra path traversal)."""
    if not NOMBRE_VALIDO.match(nombre) or ".." in nombre:
        raise ValueError("Nombre de archivo inválido")
    code, _, _ = _comando(["sh", "-c", f"rm -f {DIR_BACKUPS}/{nombre}"])
    if code != 0:
        raise RuntimeError("No se pudo eliminar el respaldo")


def restaurar_respaldo(nombre: str) -> None:
    """Restaura un respaldo (pg_restore) — PELIGROSO: sobreescribe la BD actual."""
    if not NOMBRE_VALIDO.match(nombre) or ".." in nombre:
        raise ValueError("Nombre de archivo inválido")
    code, out, _ = _comando([
        "sh", "-c",
        f"pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists {DIR_BACKUPS}/{nombre}"
    ])
    if code != 0:
        raise RuntimeError(f"pg_restore falló (exit {code}): {out[:300]}")
