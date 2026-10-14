import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from ratelimit import SlidingWindowLimiter


def test_permite_hasta_el_maximo():
    lim = SlidingWindowLimiter()

    async def run():
        ok = [await lim.allow("k", 3, 60) for _ in range(3)]
        denied = await lim.allow("k", 3, 60)
        return ok, denied

    ok, denied = asyncio.run(run())
    assert ok == [True, True, True]
    assert denied is False


def test_claves_independientes():
    lim = SlidingWindowLimiter()

    async def run():
        a = await lim.allow("ip:1", 1, 60)
        b = await lim.allow("ip:2", 1, 60)
        a2 = await lim.allow("ip:1", 1, 60)
        return a, b, a2

    a, b, a2 = asyncio.run(run())
    assert a is True and b is True and a2 is False


def test_ventana_expira():
    lim = SlidingWindowLimiter()

    async def run():
        assert await lim.allow("x", 1, 0.05) is True
        assert await lim.allow("x", 1, 0.05) is False
        await asyncio.sleep(0.08)
        assert await lim.allow("x", 1, 0.05) is True

    asyncio.run(run())
