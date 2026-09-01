# backend/docker_admin.py
# Cliente mínimo de la Docker Engine API (socket unix) para las potestades del
# administrador: ejecutar comandos (pg_dump) y leer logs de contenedores.
# NOTA: el socket se monta en el backend para este fin; el proxy de socket
# read-only (hallazgo #3 de la auditoría) sigue pendiente como endurecimiento.
import json
import httpx

DOCKER_SOCKET = "/var/run/docker.sock"
API = "/v1.43"
CONTENEDORES_VALIDOS = ("helpdesk-backend", "helpdesk-db", "helpdesk-streamlit", "n8n", "ollama")


def _client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET),
        base_url="http://localhost",
        timeout=timeout,
    )


def _demux(raw: bytes) -> tuple[bytes, bytes]:
    """Separa el stream multiplexado de Docker en (stdout, stderr)."""
    stdout, stderr = bytearray(), bytearray()
    i = 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        payload = raw[i + 8:i + 8 + size]
        (stdout if raw[i] == 1 else stderr).extend(payload)
        i += 8 + size
    return bytes(stdout), bytes(stderr)


async def exec_cmd(contenedor: str, cmd: list, timeout: float = 600.0) -> tuple[int, bytes, bytes]:
    """Ejecuta un comando en un contenedor. Devuelve (exit_code, stdout, stderr)."""
    if contenedor not in CONTENEDORES_VALIDOS:
        raise ValueError(f"Contenedor no permitido: {contenedor}")
    async with _client(timeout) as c:
        r = await c.post(f"{API}/containers/{contenedor}/exec",
                         json={"AttachStdout": True, "AttachStderr": True, "Cmd": cmd})
        r.raise_for_status()
        exec_id = r.json()["Id"]
        r = await c.post(f"{API}/exec/{exec_id}/start", json={"Detach": False, "Tty": False})
        r.raise_for_status()
        stdout, stderr = _demux(r.content)
        r = await c.get(f"{API}/exec/{exec_id}/json")
        r.raise_for_status()
        return int(r.json().get("ExitCode", 0)), stdout, stderr


async def logs(contenedor: str, tail: int = 200) -> str:
    """Lee los últimos logs de un contenedor como texto plano."""
    if contenedor not in CONTENEDORES_VALIDOS:
        raise ValueError(f"Contenedor no permitido: {contenedor}")
    async with _client(timeout=30.0) as c:
        r = await c.get(f"{API}/containers/{contenedor}/logs",
                        params={"stdout": "true", "stderr": "true", "tail": str(tail)})
        r.raise_for_status()
        out, err = _demux(r.content)
        texto = (out + err).decode("utf-8", errors="replace").strip()
        return texto or "(sin logs)"
