"""Market data API endpoints, driven through FastAPI with dependencies overridden
to the SQLite session and the mock provider (no network, no Postgres)."""
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.domains.market_data.deps import (
    get_calendar_service,
    get_market_data_service,
    get_provider_router,
)
from app.domains.market_data.enums import Exchange, SessionType, Timeframe
from app.domains.market_data.models import OHLCV
from app.domains.market_data.providers.mock import MockProvider
from app.domains.market_data.providers.registry import ProviderRouter
from app.domains.market_data.schemas import InstrumentDTO
from app.main import app
from app.models import Base


@pytest.fixture
def client() -> Iterator[TestClient]:
    # StaticPool + check_same_thread=False: TestClient runs the app on a worker
    # thread, and in-memory SQLite is otherwise bound to its creating thread.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    session = maker()

    from app.domains.market_data.cache import MarketCache
    from app.domains.market_data.calendar import MarketCalendarService
    from app.domains.market_data.service import MarketDataService

    calendar = MarketCalendarService(session, MarketCache(None))
    service = MarketDataService(
        db=session, provider=MockProvider(), cache=MarketCache(None), calendar=calendar
    )

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_market_data_service] = lambda: service
    app.dependency_overrides[get_calendar_service] = lambda: calendar
    app.dependency_overrides[get_provider_router] = lambda: ProviderRouter([MockProvider()])

    test_client = TestClient(app)
    test_client.session = session  # type: ignore[attr-defined]
    test_client.service = service  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_instruments_empty_initially(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/instruments", params={"exchange": "NSE"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_sync_then_list_instruments(client: TestClient) -> None:
    synced = client.post("/api/v1/market-data/instruments/sync", params={"exchange": "NSE"})
    assert synced.status_code == 200
    assert synced.json()["synced"] == 2

    listed = client.get("/api/v1/market-data/instruments", params={"exchange": "NSE"})
    symbols = {i["trading_symbol"] for i in listed.json()}
    assert symbols == {"RELIANCE", "TCS"}


def test_ohlcv_endpoint_returns_stored_bars(client: TestClient) -> None:
    service = client.service  # type: ignore[attr-defined]
    session = client.session  # type: ignore[attr-defined]
    instrument = service.get_or_create_instrument(InstrumentDTO(
        trading_symbol="TCS", name="TCS", exchange=Exchange.NSE
    ))
    session.add(OHLCV(
        instrument_id=instrument.id, timeframe=Timeframe.d1,
        ts=datetime(2026, 1, 5, tzinfo=UTC),
        open=100, high=105, low=99, close=102, volume=1000,
    ))
    session.commit()

    resp = client.get("/api/v1/market-data/ohlcv", params={
        "symbol": "TCS", "exchange": "NSE", "timeframe": "1d",
        "start": "2026-01-01", "end": "2026-01-31",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["close"] == 102.0


def test_latest_price_404_when_absent(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/latest-price", params={"symbol": "NOPE"})
    assert resp.status_code == 404


def test_sync_ohlcv_unknown_symbol_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/market-data/ohlcv/sync", params={
        "symbol": "NOPE", "start": "2026-01-05", "end": "2026-01-09",
    })
    assert resp.status_code == 404


def test_corporate_actions_sync_endpoint(client: TestClient) -> None:
    client.post("/api/v1/market-data/instruments/sync", params={"exchange": "NSE"})
    resp = client.post("/api/v1/market-data/corporate-actions/sync", params={"symbol": "TCS"})
    assert resp.status_code == 200
    assert resp.json()["created"] == 2


def test_calendar_sync_endpoint_loads_exchange_holidays(
    client: TestClient, monkeypatch
) -> None:  # noqa: ANN001
    """The sync endpoint reconciles whatever the exchange source reports.

    The holiday source is stubbed so this asserts endpoint wiring rather than
    NSE's live feed, which a unit test must never depend on.
    """
    from app.domains.market_data import router as router_module
    from app.domains.market_data.calendar import sync_calendar
    from app.domains.market_data.discovery.calendars import CalendarEntry

    class _StubSource:
        name = "stub_holidays"
        exchange = Exchange.NSE

        def fetch(self):  # noqa: ANN202
            return [CalendarEntry(
                calendar_date=date(2026, 1, 26),
                session_type=SessionType.holiday,
                description="Republic Day",
            )]

    monkeypatch.setattr(
        router_module, "sync_calendar", lambda db: sync_calendar(db, [_StubSource()])
    )
    synced = client.post("/api/v1/market-data/calendar/sync")
    assert synced.status_code == 200
    assert synced.json()["created"] == 1

    resp = client.get("/api/v1/market-data/calendar/trading-day",
                      params={"day": "2026-01-26", "exchange": "NSE"})
    body = resp.json()
    assert body["is_trading_day"] is False
    assert body["session_type"] == "holiday"


def test_calendar_query_normal_trading_day(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/calendar/trading-day",
                      params={"day": "2026-01-06", "exchange": "NSE"})
    body = resp.json()
    assert body["is_trading_day"] is True
    assert body["open_time"] == "09:15:00"
    assert body["close_time"] == "15:30:00"


def test_provider_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/health/providers")
    assert resp.status_code == 200
    assert resp.json()[0]["provider"] == "mock"


def test_metrics_endpoint_exposes_chain_and_hit_rate(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/health/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_chain"] == ["mock"]
    assert "counters" in body
    assert "cache_hit_rate" in body


def test_invalid_timeframe_rejected_by_validation(client: TestClient) -> None:
    resp = client.get("/api/v1/market-data/ohlcv", params={
        "symbol": "TCS", "timeframe": "7y", "start": "2026-01-01", "end": "2026-01-31",
    })
    assert resp.status_code == 422
