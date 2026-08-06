"""Unit tests for Trade Journal Engine."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.domains.analytics.enums import ExitReason
from app.domains.analytics.schemas import TradeJournalFilterRequest
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.trading.models import Portfolio, Position, Order, Fill


@pytest.fixture
def portfolio_id(db):
    p = Portfolio(name="Journal Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("100000.0000"))
    db.add(p)
    db.flush()
    return p.id


@pytest.fixture
def inst_id():
    return uuid.uuid4()


def test_record_trade_journal_entry(db, portfolio_id, inst_id):
    service = TradeJournalService()
    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(hours=2)
    exit_time = now

    costs = {
        "brokerage": "20.00",
        "stt": "30.00",
        "total_charges": "60.00",
    }

    entry = service.record_trade(
        db,
        portfolio_id=portfolio_id,
        instrument_id=inst_id,
        strategy_id="momentum_v1",
        symbol="RELIANCE",
        sector="Energy",
        entry_timestamp=entry_time,
        exit_timestamp=exit_time,
        entry_price=Decimal("2500.0000"),
        exit_price=Decimal("2600.0000"),
        quantity=Decimal("10.0000"),
        stop_loss=Decimal("2450.0000"),
        take_profit=Decimal("2700.0000"),
        exit_reason=ExitReason.take_profit,
        cost_breakdown=costs,
        market_regime="trending",
    )

    assert entry.trade_id.startswith("TJ-")
    assert entry.strategy_id == "momentum_v1"
    assert entry.gross_pnl == Decimal("1000.0000")  # (2600 - 2500) * 10
    assert entry.net_pnl == Decimal("940.0000")    # 1000 - 60
    assert entry.holding_duration_seconds == 7200
    assert entry.risk_reward_ratio == Decimal("4.0000")  # (2700-2500)/(2500-2450) = 200/50 = 4


def test_query_trade_journal_filters(db, portfolio_id, inst_id):
    service = TradeJournalService()
    now = datetime.now(timezone.utc)

    service.record_trade(
        db,
        portfolio_id=portfolio_id,
        instrument_id=inst_id,
        strategy_id="strat_a",
        symbol="TCS",
        entry_timestamp=now - timedelta(days=2),
        exit_timestamp=now - timedelta(days=2),
        entry_price=Decimal("3000.0000"),
        exit_price=Decimal("3100.0000"),
        quantity=Decimal("5.0000"),
        exit_reason=ExitReason.take_profit,
    )

    service.record_trade(
        db,
        portfolio_id=portfolio_id,
        instrument_id=inst_id,
        strategy_id="strat_b",
        symbol="INFY",
        entry_timestamp=now - timedelta(days=1),
        exit_timestamp=now - timedelta(days=1),
        entry_price=Decimal("1500.0000"),
        exit_price=Decimal("1450.0000"),
        quantity=Decimal("10.0000"),
        exit_reason=ExitReason.stop_loss,
    )

    # Filter by strategy
    req_a = TradeJournalFilterRequest(portfolio_id=portfolio_id, strategy_id="strat_a")
    trades_a = service.get_trades(db, req_a)
    assert len(trades_a) == 1
    assert trades_a[0].symbol == "TCS"

    # Filter by exit reason
    req_sl = TradeJournalFilterRequest(portfolio_id=portfolio_id, exit_reason=ExitReason.stop_loss)
    trades_sl = service.get_trades(db, req_sl)
    assert len(trades_sl) == 1
    assert trades_sl[0].symbol == "INFY"

    # Export
    export = service.export_trades(db, portfolio_id)
    assert export.total_trades == 2
