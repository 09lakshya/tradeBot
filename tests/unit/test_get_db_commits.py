"""The request-scoped session must commit, or every write endpoint is a no-op.

Regression test. `get_db` used to yield a session and only `close()` it. The OMS
services `flush()` but never commit, so rows were visible to the request that
created them -- endpoints returned 2xx and the response body showed a real id --
and were then discarded when the session closed. The whole suite passed anyway,
because the other tests assert inside the one session that did the flush.

These tests therefore verify persistence the only way that catches it: from a
*second* session opened after the dependency has finished.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import db as db_module
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType
from app.domains.market_data.models import Instrument
from app.models import Base


@pytest.fixture
def sqlite_sessionmaker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """Point `get_db` at a file-backed SQLite db, so commits outlive a session."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commit.db'}", future=True)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(db_module, "SessionLocal", lambda: maker())
    yield maker
    engine.dispose()


def _instrument(symbol: str) -> Instrument:
    return Instrument(
        trading_symbol=symbol,
        name=f"{symbol} Ltd",
        exchange=Exchange.NSE,
        instrument_type=InstrumentType.eq,
        asset_class=AssetClass.equity,
        tick_size=0.05,
        lot_size=1,
    )


def test_get_db_commits_on_success(sqlite_sessionmaker: sessionmaker[Session]) -> None:
    gen = db_module.get_db()
    session = next(gen)
    session.add(_instrument("PERSISTED"))
    session.flush()
    with pytest.raises(StopIteration):
        next(gen)  # closing the dependency must commit

    with sqlite_sessionmaker() as verify:
        found = verify.scalars(
            select(Instrument).where(Instrument.trading_symbol == "PERSISTED")
        ).all()
    assert len(found) == 1, "write was rolled back: the request session never committed"


def test_get_db_rolls_back_when_the_handler_raises(
    sqlite_sessionmaker: sessionmaker[Session],
) -> None:
    gen = db_module.get_db()
    session = next(gen)
    session.add(_instrument("DISCARDED"))
    session.flush()
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("handler blew up"))

    with sqlite_sessionmaker() as verify:
        found = verify.scalars(
            select(Instrument).where(Instrument.trading_symbol == "DISCARDED")
        ).all()
    assert found == [], "a failed request must not leave a partial write behind"
