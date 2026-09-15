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


class SpamGuard:
    """Uso normal permitido; si se supera el umbral de ráfaga (`burst_max`
    mensajes dentro de `burst_window` segundos), impone `penalty` segundos de
    bloqueo. Pensado para detectar 'spam' en el chat global."""

    def __init__(self, burst_max: int, burst_window: float, penalty: float) -> None:
        self.burst_max = burst_max
        self.burst_window = burst_window
        self.penalty = penalty
        self._hits: dict[str, deque] = defaultdict(deque)
        self._penalty_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            if now < self._penalty_until.get(key, 0.0):
                return False
            dq = self._hits[key]
            while dq and now - dq[0] > self.burst_window:
                dq.popleft()
            if len(dq) >= self.burst_max:
                # Ráfaga detectada: bloquea `penalty` segundos y reinicia el conteo.
                self._penalty_until[key] = now + self.penalty
                dq.clear()
                return False
            dq.append(now)
            return True


# Limitadores por caso de uso (claves distintas por endpoint).
login_limiter = SlidingWindowLimiter()
chat_limiter = SlidingWindowLimiter()
# Formulario de tickets: máximo 4 creaciones por hora y por usuario.
ticket_limiter = SlidingWindowLimiter()
# Chat IA: espera mínima de 3 s entre mensajes (1 evento por ventana de 3 s).
chat_ia_limiter = SlidingWindowLimiter()
# Chat global: anti-spam (máx 5 mensajes en 10 s; si se supera, 15 s de bloqueo).
chat_global_guard = SpamGuard(burst_max=5, burst_window=10, penalty=15)
