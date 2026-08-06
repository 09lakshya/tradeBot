"""Unit tests for CandidateOrder explainability and ancestry audit trail."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    PortfolioConstructionConfig,
    PortfolioSnapshot,
    SignalRankingScore,
)
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import FixedClock


def test_candidate_order_contains_full_explainability_trace():
    clock = FixedClock(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc))
    service = PortfolioConstructionService(clock=clock)

    inst_id = uuid.uuid4()
    sig = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="breakout_alpha",
        instrument_id=inst_id,
        symbol="TCS",
        timestamp=clock.now(),
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=0.92,
        entry_price=Decimal("3500.00"),
        stop_loss=Decimal("3400.00"),
        take_profit=Decimal("3750.00"),
    )

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=clock.now(),
        cash_balance=Decimal("100000.00"),
        total_equity=Decimal("100000.00"),
    )

    plan = service.construct_portfolio(
        portfolio_snapshot=snapshot,
        signals=[sig],
        current_prices={inst_id: Decimal("3500.00")},
    )

    assert len(plan.candidate_orders) == 1
    cand = plan.candidate_orders[0]

    # Verify immutability & trace
    assert cand.strategy_sources == ["breakout_alpha"]
    assert cand.signal_sources == [sig.signal_id]
    assert "explainability_trace" in cand.model_dump()
    trace = cand.explainability_trace
    assert trace["symbol"] == "TCS"
    assert "ranking_breakdown" in trace
    assert "sizing_breakdown" in trace
    assert "transaction_costs_summary" in trace
    assert len(cand.reasoning) > 10
