"""Redis client factory. Returns ``None`` when Redis is unreachable so callers
(cache, metrics) degrade gracefully instead of failing the request."""
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_redis() -> Any | None:
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 - Redis is an accelerator, not a dependency
        log.warning("redis_unavailable", error=str(exc))
        return None
