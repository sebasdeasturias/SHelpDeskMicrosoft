# backend/docker_admin.py
# Cliente mínimo de la Docker Engine API a través de un PROXY de solo lectura
# (tecnativa/docker-socket-proxy con POST deshabilitado). El backend ya NO monta
# el socket de Docker: solo puede consultar logs/inspección, nunca ejecutar
# comandos ni crear contenedores. Los respaldos se hacen con pg_dump/pg_restore
# directos contra Postgres (ver coordinator.py).
import json
import os
import httpx

DOCKER_HOST = os.getenv("DOCKER_HOST", "http://docker-socket-proxy:2375")
API = "/v1.43"
CONTENEDORES_VALIDOS = ("helpdesk-backend", "helpdesk-db", "helpdesk-streamlit", "n8n", "ollama")


def _client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=DOCKER_HOST, timeout=timeout)


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


async def logs(contenedor: str, tail: int = 200) -> str:
    """Lee los últimos logs de un contenedor como texto plano (solo lectura)."""
    if contenedor not in CONTENEDORES_VALIDOS:
        raise ValueError(f"Contenedor no permitido: {contenedor}")
    async with _client() as c:
        r = await c.get(f"{API}/containers/{contenedor}/logs",
                        params={"stdout": "true", "stderr": "true", "tail": str(tail)})
        r.raise_for_status()
        out, err = _demux(r.content)
        texto = (out + err).decode("utf-8", errors="replace").strip()
        return texto or "(sin logs)"
