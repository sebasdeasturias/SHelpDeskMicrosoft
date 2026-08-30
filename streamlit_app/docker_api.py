# streamlit_app/docker_api.py
# Lectura de logs de contenedores vía Docker Engine API (socket montado)
# con fallback a la CLI local `docker logs` cuando la app corre fuera de Docker.
import io
import json
import socket
import http.client
import subprocess
from contextlib import contextmanager

SOCKET_PATH = "/var/run/docker.sock"
API = "/v1.43"

CONTAINERS = [
    "helpdesk-backend",
    "helpdesk-db",
    "helpdesk-streamlit",
    "n8n",
    "ollama",
]


class UnixSocketConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(self.socket_path)
        self.sock = sock


@contextmanager
def _engine():
    conn = UnixSocketConnection(SOCKET_PATH)
    try:
        yield conn
    finally:
        conn.close()


def _engine_available() -> bool:
    try:
        with _engine() as conn:
            conn.request("GET", f"{API}/version")
            return conn.getresponse().status == 200
    except Exception:
        return False


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


def list_containers() -> list[dict]:
    try:
        with _engine() as conn:
            conn.request("GET", f"{API}/containers/json?all=1")
            resp = conn.getresponse()
            data = json.loads(resp.read())
            return [
                {
                    "nombre": ", ".join(n.lstrip("/") for n in c.get("Names", [])),
                    "estado": c.get("State", "?"),
                    "imagen": c.get("Image", "?"),
                }
                for c in data
            ]
    except Exception:
        try:
            out = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}|{{.Image}}"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            return [
                dict(zip(["nombre", "estado", "imagen"], line.split("|")))
                for line in out.strip().splitlines() if line
            ]
        except Exception:
            return []


def container_logs(nombre: str, tail: int = 200) -> str:
    if _engine_available():
        try:
            with _engine() as conn:
                path = f"{API}/containers/{nombre}/logs?stdout=true&stderr=true&tail={tail}"
                conn.request("GET", path)
                resp = conn.getresponse()
                raw = resp.read()
                return _demux(raw).strip() or "(sin logs)"
        except Exception as e:
            return f"[ERROR Engine API] {e}"
    try:
        out = subprocess.run(
            ["docker", "logs", "--tail", str(tail), nombre],
            capture_output=True, text=True, timeout=20,
        )
        return (out.stdout + out.stderr).strip() or "(sin logs)"
    except Exception as e:
        return f"[ERROR] No se pudo leer logs de '{nombre}': {e}"
