"""Redis fast cache with in-memory fallback (so v1 runs without a Redis server)."""
from __future__ import annotations
import json
import time

from app.utils.domain import cache_key, override_key

try:
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None


class Cache:
    def __init__(self, redis_url: str = ""):
        self.redis_url = redis_url
        self._redis = None
        self._mem: dict[str, tuple[float, str]] = {}

    async def connect(self) -> None:
        if not self.redis_url or aioredis is None:
            return
        try:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception:
            self._redis = None  # fall back to memory

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None

    # ---- generic ----
    async def _get(self, key: str) -> dict | None:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                pass
        item = self._mem.get(key)
        if not item:
            return None
        exp, raw = item
        if exp < time.time():
            self._mem.pop(key, None)
            return None
        return json.loads(raw)

    async def _set(self, key: str, value: dict, ttl: int) -> None:
        raw = json.dumps(value)
        if self._redis is not None:
            try:
                await self._redis.setex(key, ttl, raw)
                return
            except Exception:
                pass
        self._mem[key] = (time.time() + ttl, raw)

    async def _delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception:
                pass
        self._mem.pop(key, None)

    # ---- classification ----
    async def get_decision(self, domain: str) -> dict | None:
        return await self._get(cache_key(domain))

    async def set_decision(self, domain: str, payload: dict, ttl: int) -> None:
        await self._set(cache_key(domain), payload, ttl)

    # ---- overrides (persisted in SQLite too; Redis is the fast copy) ----
    async def get_override(self, domain: str) -> dict | None:
        return await self._get(override_key(domain))

    async def set_override(self, domain: str, payload: dict, ttl: int = 86400 * 30) -> None:
        await self._set(override_key(domain), payload, ttl)

    async def delete_override(self, domain: str) -> None:
        await self._delete(override_key(domain))

    async def invalidate(self, domain: str | None = None, all: bool = False) -> int:
        if all:
            n = 0
            if self._redis is not None:
                try:
                    async for key in self._redis.scan_iter("website:classification:*"):
                        await self._redis.delete(key)
                        n += 1
                except Exception:
                    pass
            keys = [k for k in self._mem if k.startswith("website:classification:")]
            for k in keys:
                self._mem.pop(k, None)
            return n + len(keys)
        if domain:
            await self._delete(cache_key(domain))
            return 1
        return 0
