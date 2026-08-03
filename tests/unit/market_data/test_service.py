"""MarketDataService behaviour that does not require Postgres.

The bar-upsert path uses the Postgres ``ON CONFLICT`` dialect and is covered by
``tests/integration/test_market_data_pipeline.py``; everything else — instrument
resolution, corporate-action persistence, reads, and caching — is exercised here
against SQLite.
"""
from datetime import UTC, date, datetime

import pytest

from app.domains.market_data.cache import MarketCache
from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.enums import CorporateActionType, Exchange, Timeframe
from app.domains.market_data.models import OHLCV, Instrument
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.providers.mock import MockProvider
from app.domains.market_data.schemas import InstrumentDTO
from app.domains.market_data.service import MarketDataService


@pytest.fixture
def service(db):  # noqa: ANN001, ANN201
    return MarketDataService(
        db=db, provider=MockProvider(), cache=MarketCache(None),
        metrics=MetricsCollector(), calendar=MarketCalendarService(db),
    )


def _tcs() -> InstrumentDTO:
    return InstrumentDTO(
        trading_symbol="TCS", name="Tata Consultancy Services",
        exchange=Exchange.NSE, isin="INE467B01029",
    )


def test_get_or_create_instrument_creates(service, db) -> None:  # noqa: ANN001
    instrument = service.get_or_create_instrument(_tcs())
    assert instrument.id is not None
    assert db.query(Instrument).count() == 1


def test_get_or_create_instrument_is_idempotent(service, db) -> None:  # noqa: ANN001
    first = service.get_or_create_instrument(_tcs())
    second = service.get_or_create_instrument(_tcs())
    assert first.id == second.id
    assert db.query(Instrument).count() == 1


def test_resolve_instrument_found_and_missing(service) -> None:  # noqa: ANN001
    service.get_or_create_instrument(_tcs())
    assert service.resolve_instrument("TCS", Exchange.NSE) is not None
    assert service.resolve_instrument("NOPE", Exchange.NSE) is None


def test_sync_instruments_populates_master(service, db) -> None:  # noqa: ANN001
    count = service.sync_instruments(Exchange.NSE)
    assert count == 2
    assert db.query(Instrument).count() == 2


def test_active_instruments_excludes_delisted(service, db) -> None:  # noqa: ANN001
    service.sync_instruments(Exchange.NSE)
    stale = db.query(Instrument).first()
    stale.is_delisted = True
    db.commit()
    active = service.active_instruments(Exchange.NSE)
    assert all(not i.is_delisted for i in active)
    assert len(active) == 1


def test_sync_corporate_actions_persists(service) -> None:  # noqa: ANN001
    service.get_or_create_instrument(_tcs())
    created = service.sync_corporate_actions("TCS", Exchange.NSE)
    assert created == 2   # mock provider returns a split + a dividend


def test_sync_corporate_actions_is_idempotent(service) -> None:  # noqa: ANN001
    service.get_or_create_instrument(_tcs())
    service.sync_corporate_actions("TCS", Exchange.NSE)
    assert service.sync_corporate_actions("TCS", Exchange.NSE) == 0


def test_sync_corporate_actions_unknown_symbol_is_noop(service) -> None:  # noqa: ANN001
    assert service.sync_corporate_actions("NOPE", Exchange.NSE) == 0


def test_load_corporate_actions_roundtrip(service) -> None:  # noqa: ANN001
    instrument = service.get_or_create_instrument(_tcs())
    service.sync_corporate_actions("TCS", Exchange.NSE)
    actions = service.load_corporate_actions(instrument.id)
    kinds = {a.action_type for a in actions}
    assert CorporateActionType.split in kinds
    assert CorporateActionType.dividend in kinds


def test_get_ohlcv_returns_stored_bars(service, db) -> None:  # noqa: ANN001
    instrument = service.get_or_create_instrument(_tcs())
    db.add(OHLCV(
        instrument_id=instrument.id, timeframe=Timeframe.d1,
        ts=datetime(2026, 1, 5, tzinfo=UTC),
        open=100, high=105, low=99, close=102, volume=1000, provider="mock",
    ))
    db.commit()
    bars = service.get_ohlcv("TCS", Exchange.NSE, Timeframe.d1,
                             date(2026, 1, 1), date(2026, 1, 31))
    assert len(bars) == 1
    assert bars[0].close == 102.0


def test_get_ohlcv_unknown_instrument_returns_empty(service) -> None:  # noqa: ANN001
    assert service.get_ohlcv("NOPE", Exchange.NSE, Timeframe.d1,
                             date(2026, 1, 1), date(2026, 1, 31)) == []


def test_get_ohlcv_respects_date_window(service, db) -> None:  # noqa: ANN001
    instrument = service.get_or_create_instrument(_tcs())
    for day in (5, 20):
        db.add(OHLCV(
            instrument_id=instrument.id, timeframe=Timeframe.d1,
            ts=datetime(2026, 1, day, tzinfo=UTC),
            open=100, high=105, low=99, close=100 + day, volume=1000,
        ))
    db.commit()
    bars = service.get_ohlcv("TCS", Exchange.NSE, Timeframe.d1,
                             date(2026, 1, 1), date(2026, 1, 10))
    assert len(bars) == 1
    assert bars[0].close == 105.0


def test_get_latest_price_returns_most_recent_close(service, db) -> None:  # noqa: ANN001
    instrument = service.get_or_create_instrument(_tcs())
    for day, close in ((5, 100.0), (6, 111.0)):
        db.add(OHLCV(
            instrument_id=instrument.id, timeframe=Timeframe.d1,
            ts=datetime(2026, 1, day, tzinfo=UTC),
            open=100, high=120, low=90, close=close, volume=1000,
        ))
    db.commit()
    assert service.get_latest_price("TCS", Exchange.NSE) == 111.0


def test_get_latest_price_missing_returns_none(service) -> None:  # noqa: ANN001
    assert service.get_latest_price("NOPE", Exchange.NSE) is None


def test_sync_ohlcv_rejects_unknown_instrument(service) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match="unknown instrument"):
        service.sync_ohlcv("NOPE", Exchange.NSE, Timeframe.d1,
                           date(2026, 1, 5), date(2026, 1, 9))
