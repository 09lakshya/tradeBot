"""Redis-backed market cache with configurable TTLs and graceful degradation.

If Redis is unavailable, every operation becomes a no-op (misses on read, silent
on write) so the application keeps serving from the database — the cache is an
accelerator, never a dependency. Cache hit/miss is recorded for observability.
"""
import json
from typing import Any

from app.core.logging import get_logger
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics

log = get_logger(__name__)

# Configurable TTLs (seconds) per cache namespace (spec §7).
DEFAULT_TTLS = {
    "latest_price": 5,
    "active_instruments": 900,
    "recent_ohlcv": 60,
    "indicator": 120,
    "provider_response": 30,
    "calendar": 86400,
}


class MarketCache:
    def __init__(
        self,
        redis_client: Any | None = None,
        ttls: dict[str, int] | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._redis = redis_client
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._metrics = metrics or default_metrics

    @property
    def available(self) -> bool:
        return self._redis is not None

    def _key(self, namespace: str, *parts: str) -> str:
        return "md:" + ":".join([namespace, *parts])

    def get(self, namespace: str, *parts: str) -> Any | None:
        if self._redis is None:
            self._metrics.incr("cache_miss", namespace=namespace)
            return None
        key = self._key(namespace, *parts)
        try:
            raw = self._redis.get(key)
        except Exception as exc:  # noqa: BLE001 - never let cache break the caller
            log.warning("cache_get_failed", key=key, error=str(exc))
            self._metrics.incr("cache_miss", namespace=namespace)
            return None
        if raw is None:
            self._metrics.incr("cache_miss", namespace=namespace)
            return None
        self._metrics.incr("cache_hit", namespace=namespace)
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def set(self, namespace: str, value: Any, *parts: str, ttl: int | None = None) -> None:
        if self._redis is None:
            return
        key = self._key(namespace, *parts)
        expire = ttl if ttl is not None else self._ttls.get(namespace, 60)
        try:
            self._redis.setex(key, expire, json.dumps(value, default=str))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_set_failed", key=key, error=str(exc))

    def invalidate(self, namespace: str, *parts: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._key(namespace, *parts))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache_invalidate_failed", error=str(exc))
