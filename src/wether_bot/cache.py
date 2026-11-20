"""Shared forecast cache with optional Redis and in-process fallback."""
import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, TypeVar

from .config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T")


class Cache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._memory: dict[str, tuple[float, str]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._redis = None

    async def start(self) -> None:
        if self.settings.redis_url:
            try:
                from redis.asyncio import from_url
                self._redis = from_url(self.settings.redis_url, decode_responses=True)
                await self._redis.ping()
            except (ImportError, Exception) as exc:
                log.warning("Redis unavailable; using memory: %s", exc)
                self._redis = None

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def get(self, key: str) -> dict | None:
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                log.warning("Redis read failed: %s", exc)
        stored = self._memory.get(key)
        if stored and stored[0] > time.monotonic():
            return json.loads(stored[1])
        self._memory.pop(key, None)
        return None

    async def set(self, key: str, obj: dict) -> None:
        raw = json.dumps(obj)
        self._memory[key] = (time.monotonic() + self.settings.cache_ttl_seconds, raw)
        if self._redis:
            try:
                await self._redis.setex(key, self.settings.cache_ttl_seconds, raw)
            except Exception as exc:
                log.warning("Redis write failed: %s", exc)
        # Avoid unbounded expired-entry accumulation for many distinct locations.
        if len(self._memory) > 4096:
            now = time.monotonic()
            self._memory = {k: v for k, v in self._memory.items() if v[0] > now}

    async def get_or_set(self, key: str, producer: Callable[[], Awaitable[dict]]) -> dict:
        cached = await self.get(key)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                return cached
            data = await producer()
            await self.set(key, data)
            return data
