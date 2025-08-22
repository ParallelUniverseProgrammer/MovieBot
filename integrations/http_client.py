from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class HttpConfig:
    connect_timeout_ms: int = 3000
    read_timeout_ms: int = 10000
    total_timeout_ms: int = 15000
    max_connections: int = 100
    retry_max: int = 2
    backoff_base_ms: int = 200


class SharedHttpClient:
    _instance: Optional["SharedHttpClient"] = None

    def __init__(self, base_headers: Optional[Dict[str, str]] = None, config: Optional[HttpConfig] = None) -> None:
        cfg = config or HttpConfig()
        timeout = aiohttp.ClientTimeout(
            total=cfg.total_timeout_ms / 1000.0,
            connect=cfg.connect_timeout_ms / 1000.0,
            sock_read=cfg.read_timeout_ms / 1000.0,
        )
        
        # Enhanced connection pooling with keep-alive and connection reuse
        connector = aiohttp.TCPConnector(
            limit=cfg.max_connections,
            limit_per_host=cfg.max_connections // 4,  # Distribute connections across hosts
            keepalive_timeout=30,  # Keep connections alive for 30 seconds
            enable_cleanup_closed=True,  # Clean up closed connections
            ssl=False,
            use_dns_cache=True,  # Cache DNS lookups
            ttl_dns_cache=300,  # DNS cache TTL of 5 minutes
        )
        
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=base_headers or {},
        )
        self._cfg = cfg
        self._closed = False

    @classmethod
    def instance(cls) -> "SharedHttpClient":
        if cls._instance is None:
            cls._instance = SharedHttpClient()
        return cls._instance

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._session.close()
            SharedHttpClient._instance = None

    async def request(self, method: str, url: str, *, params: Optional[Dict[str, Any]] = None,
                      json: Any = None, headers: Optional[Dict[str, str]] = None,
                      allow_retry_on_methods: Optional[set] = None) -> aiohttp.ClientResponse:
        allow_retry_on_methods = allow_retry_on_methods or {"GET", "HEAD", "OPTIONS"}
        attempt = 0
        last_exc: Optional[Exception] = None
        start = time.time()
        while True:
            try:
                t0 = time.time()
                async with self._session.request(method, url, params=params, json=json, headers=headers) as resp:
                    duration_ms = int((time.time() - t0) * 1000)
                    status = resp.status
                    # Retry on 429/5xx for idempotent methods
                    if method.upper() in allow_retry_on_methods and status in (429, 500, 502, 503, 504):
                        body = await resp.text()
                        self._log_req(method, url, status, duration_ms, attempt, retried=True)
                        if attempt < self._cfg.retry_max:
                            await asyncio.sleep(self._backoff(attempt))
                            attempt += 1
                            continue
                        resp.release()
                        raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=status, message=body)
                    self._log_req(method, url, status, duration_ms, attempt, retried=False)
                    return resp
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                retriable = method.upper() in allow_retry_on_methods
                if retriable and attempt < self._cfg.retry_max:
                    self._log_req(method, url, -1, int((time.time() - start) * 1000), attempt, retried=True, error=str(e))
                    await asyncio.sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                self._log_req(method, url, -1, int((time.time() - start) * 1000), attempt, retried=False, error=str(e))
                raise

    def _backoff(self, attempt: int) -> float:
        # Exponential backoff with jitter
        base = self._cfg.backoff_base_ms / 1000.0
        return min(2.0, base * (2 ** attempt))

    def _log_req(self, method: str, url: str, status: int, duration_ms: int, attempt: int, retried: bool, error: Optional[str] = None) -> None:
        safe_url = url.split("?")[0]
        extra = {"method": method, "url": safe_url, "status": status, "duration_ms": duration_ms, "attempt": attempt, "retried": retried}
        if error:
            extra["error"] = error
        logger.info("http_request", extra=extra)
