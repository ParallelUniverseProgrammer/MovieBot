from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        e = self._store.get(key)
        if not e:
            return None
        if e.expires_at < time.time():
            self._store.pop(key, None)
            return None
        return e.value

    def set(self, key: str, value: Any, ttl_sec: int) -> None:
        self._store[key] = CacheEntry(value=value, expires_at=time.time() + ttl_sec)

    def cached(self, key_builder: Callable[[], str], ttl_sec: int, loader: Callable[[], Any]) -> Any:
        key = key_builder()
        v = self.get(key)
        if v is not None:
            return v
        v = loader()
        self.set(key, v, ttl_sec)
        return v


# Singleton cache for integrations
shared_cache = TTLCache()
