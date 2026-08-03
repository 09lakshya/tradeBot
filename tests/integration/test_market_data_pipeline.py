"""End-to-end ingestion pipeline against a real PostgreSQL/TimescaleDB instance.

Skipped unless ``TEST_DATABASE_URL`` is set, because the upsert path uses the
Postgres ``ON CONFLICT`` dialect and ohlcv is a hypertable. Run with:

    TEST_DATABASE_URL=postgresql+psycopg://tradebot:...@localhost:5432/tradebot_test pytest -m postgres
"""
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domains.market_data.calendar import MarketCalendarService, seed_calendar
from app.domains.market_data.enums import (
    CorporateActionType,
    Exchange,
    SessionType,
    Timeframe,
)
from app.domains.market_data.models import (
    OHLCV,
    CorporateAction,
    Instrument,
    QuarantinedData,
)
from app.domains.market_data.providers.mock import MockProvider
from app.domains.market_data.schemas import InstrumentDTO
from app.domains.market_data.service import MarketDataService
from app.models import Base

DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set"),
]

# Time-series tables promoted to TimescaleDB hypertables in the initial migration.
HYPERTABLES = ["ohlcv", "equity_snapshots"]


@pytest.fixture
def pg_db() -> Iterator[Session]:
    """A clean schema per test, built the way the migration builds it: tables from
    the ORM metadata, then the time-series tables promoted to hypertables."""
    engine = create_engine(DB_URL, future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in HYPERTABLES:
            conn.execute(
                text(
                    "SELECT create_hypertable(:t, 'ts', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                ),
                {"t": table},
            )
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def service(pg_db: Session) -> MarketDataService:
    return MarketDataService(
        db=pg_db, provider=MockProvider(),
        calendar=MarketCalendarService(pg_db),
    )


def _seed_instrument(service: MarketDataService) -> Instrument:
    return service.get_or_create_instrument(InstrumentDTO(
        trading_symbol="TCS", name="Tata Consultancy Services",
        exchange=Exchange.NSE, isin="INE467B01029",
    ))


# --- core ingestion -----------------------------------------------------
def test_full_sync_persists_bars(service: MarketDataService, pg_db: Session) -> None:
    _seed_instrument(service)
    summary = service.sync_ohlcv(
        "TCS", Exchange.NSE, Timeframe.d1, date(2026, 1, 5), date(2026, 1, 9)
    )
    assert summary["inserted"] > 0
    assert pg_db.execute(select(OHLCV)).scalars().first() is not None


def test_sync_is_idempotent(service: MarketDataService, pg_db: Session) -> None:
    _seed_instrument(service)
    args = ("TCS", Exchange.NSE, Timeframe.d1, date(2026, 1, 5), date(2026, 1, 9))
    service.sync_ohlcv(*args)
    count_first = len(pg_db.execute(select(OHLCV)).scalars().all())
    service.sync_ohlcv(*args)
    count_second = len(pg_db.execute(select(OHLCV)).scalars().all())
    assert count_first == count_second, "re-sync must upsert, not duplicate"


def test_upsert_updates_existing_row_on_conflict(
    service: MarketDataService, pg_db: Session
) -> None:
    """ON CONFLICT DO UPDATE: a re-sync with different values must overwrite the
    existing bar in place, not insert a duplicate and not leave the old value."""
    instrument = _seed_instrument(service)
    args = ("TCS", Exchange.NSE, Timeframe.d1, date(2026, 1, 5), date(2026, 1, 5))
    service.sync_ohlcv(*args)
    row = pg_db.execute(select(OHLCV)).scalars().one()
    ts, original_close = row.ts, float(row.close)

    # Same PK (instrument, timeframe, ts), different close -> must UPDATE in place.
    service._upsert_bars(instrument.id, Timeframe.d1, [_bar(ts, original_close + 100.0)], "mock")
    rows = pg_db.execute(select(OHLCV)).scalars().all()
    assert len(rows) == 1, "conflict must update, not duplicate"
    assert float(rows[0].close) == pytest.approx(original_close + 100.0)


def test_batch_insert_persists_every_bar(
    service: MarketDataService, pg_db: Session
) -> None:
    instrument = _seed_instrument(service)
    base = datetime(2026, 1, 5, 3, 45, tzinfo=UTC)
    bars = [_bar(base, 100.0 + i, minutes=i) for i in range(500)]
    inserted = service._upsert_bars(instrument.id, Timeframe.m1, bars, "mock")
    assert inserted == 500
    assert len(pg_db.execute(select(OHLCV)).scalars().all()) == 500


# --- constraints --------------------------------------------------------
def test_foreign_key_is_enforced(service: MarketDataService, pg_db: Session) -> None:
    """A bar for a non-existent instrument must be rejected by the FK, not stored."""
    import uuid
    pg_db.add(OHLCV(
        instrument_id=uuid.uuid4(), timeframe=Timeframe.d1,
        ts=datetime(2026, 1, 5, tzinfo=UTC),
        open=1, high=1, low=1, close=1, volume=1,
    ))
    with pytest.raises(IntegrityError):
        pg_db.commit()
    pg_db.rollback()


def test_composite_pk_stores_timeframes_side_by_side(
    service: MarketDataService, pg_db: Session
) -> None:
    _seed_instrument(service)
    for tf in (Timeframe.d1, Timeframe.h1):
        service.sync_ohlcv("TCS", Exchange.NSE, tf, date(2026, 1, 5), date(2026, 1, 6))
    frames = {r.timeframe for r in pg_db.execute(select(OHLCV)).scalars()}
    assert {Timeframe.d1, Timeframe.h1}.issubset(frames)


def test_timestamptz_round_trips_the_instant(
    service: MarketDataService, pg_db: Session
) -> None:
    """A bar written from an IST wall-clock time must read back as the same UTC
    instant — TIMESTAMPTZ preserves the moment, not a wall-clock string."""
    instrument = _seed_instrument(service)
    ist_instant = datetime(2026, 1, 5, 9, 15, tzinfo=UTC).astimezone()  # aware
    service._upsert_bars(instrument.id, Timeframe.m1, [_bar(ist_instant, 100.0)], "mock")
    stored = pg_db.execute(select(OHLCV)).scalars().one()
    assert stored.ts.astimezone(UTC) == ist_instant.astimezone(UTC)


# --- corporate actions --------------------------------------------------
def test_corporate_action_sync_is_idempotent_and_updatable(
    service: MarketDataService, pg_db: Session
) -> None:
    _seed_instrument(service)
    created_first = service.sync_corporate_actions("TCS", Exchange.NSE)
    created_second = service.sync_corporate_actions("TCS", Exchange.NSE)
    assert created_first > 0
    assert created_second == 0, "the uq_corp_action constraint must dedupe re-syncs"

    # The is_applied flag is the adjustment-tracking update path.
    action = pg_db.execute(
        select(CorporateAction).where(
            CorporateAction.action_type == CorporateActionType.split
        )
    ).scalars().first()
    assert action is not None and action.is_applied is False
    action.is_applied = True
    pg_db.commit()
    pg_db.refresh(action)
    assert action.is_applied is True


# --- quarantine ---------------------------------------------------------
def test_calendar_mismatch_is_quarantined_not_stored(
    service: MarketDataService, pg_db: Session
) -> None:
    _seed_instrument(service)
    seed_calendar(pg_db, entries=[
        (date(2026, 1, 26), SessionType.holiday, "Republic Day"),
    ])
    service.sync_ohlcv(
        "TCS", Exchange.NSE, Timeframe.d1, date(2026, 1, 24), date(2026, 1, 28)
    )
    quarantined = pg_db.execute(select(QuarantinedData)).scalars().all()
    assert quarantined, "bars on non-trading days must be quarantined"


def test_unknown_instrument_raises(service: MarketDataService) -> None:
    with pytest.raises(ValueError, match="unknown instrument"):
        service.sync_ohlcv(
            "NOPE", Exchange.NSE, Timeframe.d1, date(2026, 1, 5), date(2026, 1, 9)
        )


# --- helpers ------------------------------------------------------------
def _bar(ts: datetime, close: float, *, minutes: int = 0):  # noqa: ANN202
    from datetime import timedelta

    from app.domains.market_data.schemas import OHLCVBar
    return OHLCVBar(
        ts=ts + timedelta(minutes=minutes),
        open=close, high=close + 1, low=close - 1, close=close,
        adjusted_close=close, volume=1000,
    )
