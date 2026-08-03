"""Dependency injection for the market data domain.

Provider selection happens here and nowhere else — switching providers is a config
change (``MARKET_DATA_PROVIDER`` / ``MARKET_DATA_FALLBACKS``), never a code change.
"""
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.market_data.cache import MarketCache
from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.observability import metrics
from app.domains.market_data.providers.registry import ProviderRouter, build_router
from app.domains.market_data.providers.resilience import RetryPolicy
from app.domains.market_data.service import MarketDataService


@lru_cache
def get_provider_router() -> ProviderRouter:
    """Build the configured failover chain once per process."""
    router = build_router(
        primary=settings.market_data_provider,
        fallbacks=settings.market_data_fallback_list,
        metrics=metrics,
    )
    router._retry = RetryPolicy(max_attempts=settings.market_data_max_retries)  # noqa: SLF001
    return router


def get_cache() -> MarketCache:
    return MarketCache(redis_client=get_redis(), metrics=metrics)


def get_calendar_service(db: Session = Depends(get_db)) -> MarketCalendarService:
    return MarketCalendarService(db, get_cache())


def get_market_data_service(db: Session = Depends(get_db)) -> MarketDataService:
    cache = get_cache()
    return MarketDataService(
        db=db,
        provider=get_provider_router(),
        cache=cache,
        metrics=metrics,
        calendar=MarketCalendarService(db, cache),
    )
