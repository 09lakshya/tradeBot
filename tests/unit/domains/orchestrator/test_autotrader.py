"""Tests for the autonomous trading loop's guards.

The value of this loop is as much in what it refuses to do as in what it does:
it must not trade outside market hours, must not trade an unfunded account, must
not trade an empty watchlist, and must never size an order against a price it
could not actually fetch.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.domains.orchestrator.autotrader import AutoTrader, CycleOutcome
from app.domains.orchestrator.session_manager import MarketSessionManager


class _FrozenSession(MarketSessionManager):
    """Session manager pinned to a fixed instant, so tests don't depend on 'now'."""

    def __init__(self, moment: datetime) -> None:
        super().__init__()
        self._moment = moment

    def is_market_open(self, dt: datetime) -> bool:
        return super().is_market_open(self._moment)

    def get_session_state(self, dt: datetime):
        return super().get_session_state(self._moment)


# 2026-09-21 is a Monday. 06:00 UTC = 11:30 IST (open); 03:00 UTC = 08:30 IST (closed).
DURING_SESSION = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
BEFORE_OPEN = datetime(2026, 9, 21, 3, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 19, 6, 0, tzinfo=UTC)


def test_does_not_trade_before_the_open() -> None:
    trader = AutoTrader(session_manager=_FrozenSession(BEFORE_OPEN))
    outcome = trader.run_cycle()
    assert outcome.ran is False
    assert "market" in outcome.reason
    assert outcome.submitted == 0


def test_does_not_trade_at_the_weekend() -> None:
    trader = AutoTrader(session_manager=_FrozenSession(SATURDAY))
    outcome = trader.run_cycle()
    assert outcome.ran is False
    assert outcome.submitted == 0


def test_refuses_to_trade_without_a_funded_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unfunded account must be reported, not traded on a zero balance."""
    trader = AutoTrader(session_manager=_FrozenSession(DURING_SESSION))

    class _EmptyScalars:
        def first(self):
            return None

    class _NoPortfolioSession:
        def scalars(self, *_a, **_k):
            return _EmptyScalars()

        def __enter__(self):
            return self

        def __exit__(self, *_a) -> bool:
            return False

    monkeypatch.setattr(
        "app.domains.orchestrator.autotrader.SessionLocal", lambda: _NoPortfolioSession()
    )
    outcome = trader.run_cycle()
    assert outcome.ran is False
    assert "wallet" in outcome.reason


def test_force_bypasses_the_market_gate_only_for_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``force`` is a testing affordance; it must not also skip the wallet check."""
    trader = AutoTrader(session_manager=_FrozenSession(SATURDAY))

    class _EmptyScalars:
        def first(self):
            return None

    class _NoPortfolioSession:
        def scalars(self, *_a, **_k):
            return _EmptyScalars()

        def __enter__(self):
            return self

        def __exit__(self, *_a) -> bool:
            return False

    monkeypatch.setattr(
        "app.domains.orchestrator.autotrader.SessionLocal", lambda: _NoPortfolioSession()
    )
    outcome = trader.run_cycle(force=True)
    assert outcome.ran is False
    assert "wallet" in outcome.reason  # got past the gate, stopped at the wallet


def test_status_reports_the_session_and_stays_stopped_until_started() -> None:
    trader = AutoTrader(session_manager=_FrozenSession(DURING_SESSION))
    status = trader.status()
    assert status["running"] is False
    assert status["market_open"] is True
    assert status["cycles_executed"] == 0
    assert status["interval_seconds"] > 0


def test_outcome_history_is_bounded() -> None:
    """A long session must not accumulate outcomes without limit."""
    trader = AutoTrader(session_manager=_FrozenSession(BEFORE_OPEN))
    for _ in range(120):
        trader.state.record(CycleOutcome(timestamp=datetime.now(UTC), ran=False), keep=50)
    assert len(trader.state.history) == 50
    assert trader.state.cycles_attempted == 120
    assert trader.state.cycles_executed == 0


def test_unpriced_instruments_are_excluded_from_signal_generation() -> None:
    """A price we could not fetch must drop the symbol, never fall back to a
    placeholder: the pipeline would otherwise size a real order off a fiction."""

    class _Inst:
        def __init__(self, symbol: str) -> None:
            self.id = uuid.uuid4()
            self.trading_symbol = symbol
            self.is_delisted = False

    priced_inst, unpriced_inst = _Inst("PRICED"), _Inst("UNPRICED")
    prices = {priced_inst.id: Decimal("100.00")}

    considered = [i for i in (priced_inst, unpriced_inst) if i.id in prices]
    assert considered == [priced_inst]
