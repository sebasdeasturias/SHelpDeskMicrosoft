# backend/ratelimit.py
# Limitador de tasa en memoria (ventana deslizante), sin dependencias externas.
#
# IMPORTANTE (honestidad técnica): al ser en memoria, el límite es POR PROCESO.
# Es correcto si el backend corre con un solo worker de uvicorn (workers=1, como
# en docker-compose.prod.yml). Si algún día escalas a varios workers o réplicas,
# habrá que migrar este límite a un almacén compartido (Redis u otro).
import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Permite hasta `max_events` ocurrencias por `window_seconds` por clave."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_prune = 0.0

    async def allow(self, key: str, max_events: int, window_seconds: float) -> bool:
        """Registra el intento y devuelve True si aún no se superó el límite."""
        now = time.monotonic()
        async with self._lock:
            if now - self._last_prune > 60:
                self._prune(now)
            dq = self._hits[key]
            while dq and now - dq[0] > window_seconds:
                dq.popleft()
            if len(dq) >= max_events:
                return False
            dq.append(now)
            return True

    def _prune(self, now: float) -> None:
        empty = []
        for key, dq in self._hits.items():
            while dq and now - dq[0] > 3600:
                dq.popleft()
            if not dq:
                empty.append(key)
        for key in empty:
            del self._hits[key]
        self._last_prune = now


# Limitadores por caso de uso (claves distintas por endpoint).
login_limiter = SlidingWindowLimiter()
chat_limiter = SlidingWindowLimiter()
