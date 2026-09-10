# streamlit_app/docker_api.py
# Acceso de SOLO LECTURA a la Docker Engine API a través del proxy
# docker-socket-proxy (POST deshabilitado). El panel ya NO monta el socket de
# Docker: solo puede listar contenedores y leer logs, nunca ejecutar comandos.
import io
import os
import requests

DOCKER_HOST = os.getenv("DOCKER_HOST", "http://docker-socket-proxy:2375").rstrip("/")
API = "/v1.43"

CONTAINERS = [
    "helpdesk-backend",
    "helpdesk-db",
    "helpdesk-streamlit",
    "n8n",
    "ollama",
]


def _get(path: str, **params):
    return requests.get(f"{DOCKER_HOST}{API}{path}", params=params, timeout=15)


def list_containers() -> list[dict]:
    try:
        data = _get("/containers/json", all=1).json()
        return [
            {
                "nombre": ", ".join(n.lstrip("/") for n in c.get("Names", [])),
                "estado": c.get("State", "?"),
                "imagen": c.get("Image", "?"),
            }
            for c in data
        ]
    except Exception:
        return []


def _demux(raw: bytes) -> str:
    """Convierte el stream multiplexado del Engine API en texto plano."""
    buf = io.BytesIO(raw)
    out = []
    while True:
        header = buf.read(8)
        if len(header) < 8:
            break
        size = int.from_bytes(header[4:8], "big")
        out.append(buf.read(size).decode("utf-8", errors="replace"))
    return "".join(out)


def container_logs(nombre: str, tail: int = 200) -> str:
    try:
        raw = _get(f"/containers/{nombre}/logs", stdout="true", stderr="true", tail=str(tail)).content
        return _demux(raw).strip() or "(sin logs)"
    except Exception as e:
        return f"[ERROR] No se pudo leer logs de '{nombre}': {e}"
