"""Market data API endpoints, including observability/health surfaces."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.market_data.calendar import MarketCalendarService, sync_calendar
from app.domains.market_data.deps import (
    get_calendar_service,
    get_market_data_service,
    get_provider_router,
)
from app.domains.market_data.enums import Exchange, SessionType, Timeframe
from app.domains.market_data.observability import metrics
from app.domains.market_data.providers.registry import ProviderRouter, available_providers
from app.domains.market_data.schemas import OHLCVBar, ProviderHealth
from app.domains.market_data.service import MarketDataService

router = APIRouter()


class SyncResult(BaseModel):
    fetched: int
    valid: int
    quarantined: int
    missing_intervals: int
    inserted: int


class InstrumentOut(BaseModel):
    trading_symbol: str
    name: str
    exchange: Exchange
    sector: str | None = None
    isin: str | None = None
    is_active: bool


class TradingDayOut(BaseModel):
    exchange: Exchange
    day: date
    is_trading_day: bool
    session_type: SessionType
    open_time: str | None = None
    close_time: str | None = None


# --- instruments --------------------------------------------------------
@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(
    exchange: Exchange = Query(Exchange.NSE),
    service: MarketDataService = Depends(get_market_data_service),
) -> list[InstrumentOut]:
    return [
        InstrumentOut(
            trading_symbol=i.trading_symbol, name=i.name, exchange=i.exchange,
            sector=i.sector, isin=i.isin, is_active=i.is_active,
        )
        for i in service.active_instruments(exchange)
    ]


@router.post("/instruments/sync")
def sync_instruments(
    exchange: Exchange = Query(Exchange.NSE),
    service: MarketDataService = Depends(get_market_data_service),
) -> dict[str, int]:
    return {"synced": service.sync_instruments(exchange)}


# --- OHLCV --------------------------------------------------------------
@router.get("/ohlcv", response_model=list[OHLCVBar])
def get_ohlcv(
    symbol: str,
    start: date,
    end: date,
    exchange: Exchange = Query(Exchange.NSE),
    timeframe: Timeframe = Query(Timeframe.d1),
    service: MarketDataService = Depends(get_market_data_service),
) -> list[OHLCVBar]:
    return service.get_ohlcv(symbol, exchange, timeframe, start, end)


@router.post("/ohlcv/sync", response_model=SyncResult)
def sync_ohlcv(
    symbol: str,
    start: date,
    end: date,
    exchange: Exchange = Query(Exchange.NSE),
    timeframe: Timeframe = Query(Timeframe.d1),
    service: MarketDataService = Depends(get_market_data_service),
) -> SyncResult:
    try:
        return SyncResult(**service.sync_ohlcv(symbol, exchange, timeframe, start, end))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/latest-price")
def latest_price(
    symbol: str,
    exchange: Exchange = Query(Exchange.NSE),
    service: MarketDataService = Depends(get_market_data_service),
) -> dict[str, object]:
    price = service.get_latest_price(symbol, exchange)
    if price is None:
        raise HTTPException(status_code=404, detail=f"no price for {symbol}")
    return {"symbol": symbol, "exchange": exchange, "price": price}


# --- corporate actions --------------------------------------------------
@router.post("/corporate-actions/sync")
def sync_corporate_actions(
    symbol: str,
    exchange: Exchange = Query(Exchange.NSE),
    service: MarketDataService = Depends(get_market_data_service),
) -> dict[str, int]:
    return {"created": service.sync_corporate_actions(symbol, exchange)}


# --- calendar -----------------------------------------------------------
@router.get("/calendar/trading-day", response_model=TradingDayOut)
def trading_day(
    day: date,
    exchange: Exchange = Query(Exchange.NSE),
    calendar: MarketCalendarService = Depends(get_calendar_service),
) -> TradingDayOut:
    hours = calendar.trading_hours(exchange, day)
    return TradingDayOut(
        exchange=exchange, day=day,
        is_trading_day=calendar.is_trading_day(exchange, day),
        session_type=calendar.session_type(exchange, day),
        open_time=hours[0].isoformat() if hours else None,
        close_time=hours[1].isoformat() if hours else None,
    )


@router.post("/calendar/sync")
def sync_market_calendar(db: Session = Depends(get_db)) -> dict[str, int]:
    """Refresh the trading calendar from each exchange's published holiday master."""
    return sync_calendar(db)


# --- observability / health --------------------------------------------
@router.get("/health/providers", response_model=list[ProviderHealth])
def provider_health(
    provider_router: ProviderRouter = Depends(get_provider_router),
) -> list[ProviderHealth]:
    return provider_router.health_all()


@router.get("/health/metrics")
def market_data_metrics(
    provider_router: ProviderRouter = Depends(get_provider_router),
) -> dict[str, object]:
    snapshot = metrics.snapshot()
    counters: dict[str, float] = snapshot.get("counters", {})
    hits = sum(v for k, v in counters.items() if k.startswith("cache_hit"))
    misses = sum(v for k, v in counters.items() if k.startswith("cache_miss"))
    total = hits + misses
    return {
        **snapshot,
        "cache_hit_rate": round(hits / total, 4) if total else None,
        "provider_chain": provider_router.chain,
        "registered_providers": available_providers(),
    }
