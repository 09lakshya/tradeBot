"""Market data ingestion tasks.

The EOD sync is calendar-aware: it asks the Market Calendar whether the exchange
actually traded before doing any work, so no schedule embeds holiday logic.
"""
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.domains.market_data.cache import MarketCache
from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.deps import get_provider_router
from app.domains.market_data.enums import Exchange, Timeframe
from app.domains.market_data.observability import metrics
from app.domains.market_data.service import MarketDataService
from app.workers.celery_app import celery

log = get_logger(__name__)


def _service(db: Session) -> MarketDataService:
    cache = MarketCache(redis_client=get_redis(), metrics=metrics)
    return MarketDataService(
        db=db, provider=get_provider_router(), cache=cache,
        metrics=metrics, calendar=MarketCalendarService(db, cache),
    )


@celery.task(name="market_data.sync_symbol", bind=True, max_retries=3)
def sync_symbol(
    self: Any,
    symbol: str,
    exchange: str = "NSE",
    timeframe: str = "1d",
    days: int = 30,
) -> dict[str, int]:
    """Sync one symbol's bars for the trailing ``days`` window."""
    db = SessionLocal()
    try:
        service = _service(db)
        end = date.today()
        start = end - timedelta(days=days)
        return service.sync_ohlcv(
            symbol, Exchange(exchange), Timeframe(timeframe), start, end
        )
    except Exception as exc:  # noqa: BLE001 - retry with backoff via Celery
        log.error("sync_symbol_failed", symbol=symbol, error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery.task(name="market_data.sync_eod")
def sync_eod(exchange: str = "NSE", timeframe: str = "1d") -> dict[str, object]:
    """Daily end-of-day sync for every active instrument on an exchange."""
    db = SessionLocal()
    try:
        exch = Exchange(exchange)
        calendar = MarketCalendarService(db, MarketCache(redis_client=get_redis()))
        today = date.today()
        if not calendar.is_trading_day(exch, today):
            log.info("sync_eod_skipped", reason="non-trading day", day=str(today))
            return {"skipped": True, "reason": "non-trading day", "date": str(today)}

        service = _service(db)
        instruments = service.active_instruments(exch)
        queued = 0
        for instrument in instruments:
            sync_symbol.delay(instrument.trading_symbol, exchange, timeframe, 5)
            queued += 1
        log.info("sync_eod_queued", exchange=exchange, count=queued)
        return {"skipped": False, "queued": queued, "date": str(today)}
    finally:
        db.close()


@celery.task(name="market_data.sync_corporate_actions")
def sync_corporate_actions(exchange: str = "NSE") -> dict[str, int]:
    """Refresh corporate actions for all active instruments."""
    db = SessionLocal()
    try:
        service = _service(db)
        exch = Exchange(exchange)
        total = 0
        for instrument in service.active_instruments(exch):
            try:
                total += service.sync_corporate_actions(instrument.trading_symbol, exch)
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the run
                log.warning("corp_action_sync_failed",
                            symbol=instrument.trading_symbol, error=str(exc))
        return {"created": total}
    finally:
        db.close()


@celery.task(name="market_data.sync_universe")
def sync_universe() -> dict[str, object]:
    """Rediscover the full instrument universe from the exchanges and reconcile it.

    Runs on a slow cadence (daily/weekly): listings, delistings, and renames are
    the input, so the Instrument Master tracks the market instead of drifting from
    a one-time seed.
    """
    from app.domains.market_data.discovery import InstrumentUniverseService

    db = SessionLocal()
    try:
        service = InstrumentUniverseService(db=db, metrics=metrics)
        report, reconciliation = service.sync()
        return {"discovery": report.summary(), "reconciliation": reconciliation.summary()}
    finally:
        db.close()


@celery.task(name="market_data.sync_calendar")
def sync_calendar_task() -> dict[str, int]:
    """Refresh the trading calendar from each exchange's holiday master.

    Holiday schedules are amended mid-year (election days, unscheduled closures),
    so this is a scheduled refresh rather than a one-time seed — a stale calendar
    quarantines real bars and misreads closures as gaps.
    """
    from app.domains.market_data.calendar import sync_calendar

    db = SessionLocal()
    try:
        return sync_calendar(db)
    finally:
        db.close()


@celery.task(name="market_data.provider_health_probe")
def provider_health_probe() -> list[dict[str, object]]:
    """Periodic provider availability probe feeding the observability gauges."""
    router = get_provider_router()
    results = []
    for health in router.health_all():
        metrics.gauge(
            "provider_available",
            1.0 if health.status.value == "up" else 0.0,
            provider=health.provider,
        )
        results.append(health.model_dump(mode="json"))
    return results
