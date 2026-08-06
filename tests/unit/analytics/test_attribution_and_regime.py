"""Unit tests for Strategy Attribution and Market Regime Analysis Engine."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.enums import MarketRegimeClassification
from app.domains.analytics.regime import MarketRegimeAnalyzer
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.trading.models import Portfolio


@pytest.fixture
def portfolio(db):
    p = Portfolio(name="Attribution Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("100000.0000"))
    db.add(p)
    db.flush()
    return p


def test_strategy_attribution_and_leaderboard(db, portfolio):
    journal = TradeJournalService()
    attr_service = StrategyAttributionService()
    now = datetime.now(timezone.utc)
    inst1, inst2 = uuid.uuid4(), uuid.uuid4()

    # Strategy 1 trades (winning)
    for i in range(3):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst1,
            strategy_id="strat_win", symbol="HDFCBANK",
            entry_timestamp=now - timedelta(days=5 - i), exit_timestamp=now - timedelta(days=5 - i),
            entry_price=Decimal("1500.0000"), exit_price=Decimal("1550.0000"),
            quantity=Decimal("10.0000"), cost_breakdown={"total_charges": "20.00"},
        )

    # Strategy 2 trades (losing)
    for i in range(2):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst2,
            strategy_id="strat_loss", symbol="WIPRO",
            entry_timestamp=now - timedelta(days=3 - i), exit_timestamp=now - timedelta(days=3 - i),
            entry_price=Decimal("400.0000"), exit_price=Decimal("380.0000"),
            quantity=Decimal("50.0000"), cost_breakdown={"total_charges": "15.00"},
        )

    report_win = attr_service.get_strategy_attribution(db, portfolio.id, "strat_win")
    assert report_win.total_trades == 3
    assert report_win.win_rate_pct == 100.0
    assert report_win.net_pnl == Decimal("1440.0000")  # (500*3) - 60

    leaderboard = attr_service.get_strategy_leaderboard(db, portfolio.id)
    assert len(leaderboard) == 2
    assert leaderboard[0].strategy_id == "strat_win"
    assert leaderboard[1].strategy_id == "strat_loss"


def test_regime_classification_and_statistics(db, portfolio):
    analyzer = MarketRegimeAnalyzer()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    # Test quantitative classification
    assert analyzer.classify_regime(volatility=0.8) == MarketRegimeClassification.high_volatility
    assert analyzer.classify_regime(volatility=0.2) == MarketRegimeClassification.low_volatility
    assert analyzer.classify_regime(volatility=0.5, trend_strength=0.6, direction=0.4) == MarketRegimeClassification.bullish

    # Record trades with regimes
    journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst_id,
        strategy_id="s1", symbol="SBIN",
        entry_timestamp=now, exit_timestamp=now,
        entry_price=Decimal("500.0000"), exit_price=Decimal("520.0000"),
        quantity=Decimal("20.0000"), market_regime="trending_bullish",
    )

    stats = analyzer.get_regime_statistics(db, portfolio.id)
    assert len(stats.regime_stats) == 1
    assert stats.regime_stats[0].regime == "trending_bullish"
    assert stats.regime_stats[0].win_rate_pct == 100.0
