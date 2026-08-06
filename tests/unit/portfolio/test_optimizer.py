"""Unit tests for PortfolioOptimizer."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.enums import AllocationPolicyType, ArbitrationMethod
from app.domains.portfolio.optimizer import PortfolioOptimizer
from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    PortfolioConstructionConfig,
    PortfolioSnapshot,
    PositionSnapshot,
    SignalRankingScore,
)
from app.domains.strategies.enums import SignalDirection
from app.domains.trading.enums import OrderSide


def create_decision(inst_id: uuid.UUID, symbol: str, sig_id: uuid.UUID) -> ArbitrationDecision:
    return ArbitrationDecision(
        instrument_id=inst_id,
        symbol=symbol,
        winning_side=OrderSide.buy,
        selected_signals=[sig_id],
        discarded_signals=[],
        blended_confidence=0.9,
        blended_entry_price=Decimal("100.00"),
        blended_stop_loss=Decimal("95.00"),
        blended_take_profit=Decimal("110.00"),
        conflict_type="NO_CONFLICT",
        resolution_method=ArbitrationMethod.net_confidence_weighted,
        reason="Test",
    )


def test_optimizer_respects_cash_reserve_and_caps():
    optimizer = PortfolioOptimizer()
    inst1, inst2 = uuid.uuid4(), uuid.uuid4()
    sig1, sig2 = uuid.uuid4(), uuid.uuid4()

    decisions = [
        create_decision(inst1, "TCS", sig1),
        create_decision(inst2, "INFY", sig2),
    ]

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
    )

    config = PortfolioConstructionConfig(
        reserve_cash_pct=Decimal("0.1000"),      # 10% cash reserve -> 90% budget
        max_portfolio_exposure=Decimal("0.9000"),
        max_instrument_weight=Decimal("0.0800"),  # Cap at 8% per stock
        allocation_policy=AllocationPolicyType.equal_weight,
    )

    weights, explanations = optimizer.optimize(
        decisions=decisions,
        snapshot=snapshot,
        ranking_scores={},
        config=config,
    )

    # Equal weight would give 45% each, but capped at 8%
    assert weights[inst1] == Decimal("0.0800")
    assert weights[inst2] == Decimal("0.0800")
    assert "Capped at max instrument limit" in explanations[str(inst1)]


def test_optimizer_enforces_sector_limits():
    optimizer = PortfolioOptimizer()
    inst1, inst2 = uuid.uuid4(), uuid.uuid4()
    sig1, sig2 = uuid.uuid4(), uuid.uuid4()

    decisions = [
        create_decision(inst1, "HDFC", sig1),
        create_decision(inst2, "ICICI", sig2),
    ]

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
    )

    config = PortfolioConstructionConfig(
        max_instrument_weight=Decimal("0.2000"),
        max_sector_weight=Decimal("0.2500"),  # Banking sector capped at 25%
        allocation_policy=AllocationPolicyType.equal_weight,
    )

    sectors = {inst1: "Banking", inst2: "Banking"}

    # Ranking score to prioritize inst1
    ranking_scores = {
        sig1: SignalRankingScore(
            signal_id=sig1, instrument_id=inst1, symbol="HDFC", strategy_id="s",
            direction=SignalDirection.long, composite_score=0.9, rank=1, explanation=""
        ),
        sig2: SignalRankingScore(
            signal_id=sig2, instrument_id=inst2, symbol="ICICI", strategy_id="s",
            direction=SignalDirection.long, composite_score=0.7, rank=2, explanation=""
        ),
    }

    weights, explanations = optimizer.optimize(
        decisions=decisions,
        snapshot=snapshot,
        ranking_scores=ranking_scores,
        config=config,
        instrument_sectors=sectors,
    )

    # Inst 1 gets 20%
    assert weights[inst1] == Decimal("0.2000")
    # Inst 2 gets remaining 5% of 25% sector cap
    assert weights[inst2] == Decimal("0.0500")
    assert "Capped at remaining sector budget" in explanations[str(inst2)]


def test_optimizer_suppresses_trades_within_rebalance_deadband():
    optimizer = PortfolioOptimizer()
    inst1 = uuid.uuid4()
    sig1 = uuid.uuid4()

    decisions = [create_decision(inst1, "TCS", sig1)]

    # Existing holding is 9.8%
    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("90200"),
        total_equity=Decimal("100000"),
        current_weights={inst1: Decimal("0.0980")},
    )

    # Target weight is 10.0% (delta = 0.2% < 1.5% deadband)
    config = PortfolioConstructionConfig(
        max_instrument_weight=Decimal("0.1000"),
        rebalance_deadband_pct=Decimal("0.0150"),
        allocation_policy=AllocationPolicyType.equal_weight,
    )

    weights, explanations = optimizer.optimize(
        decisions=decisions,
        snapshot=snapshot,
        ranking_scores={},
        config=config,
    )

    # Rebalance suppressed due to deadband
    assert inst1 not in weights
    assert "Turnover deadband active" in explanations[str(inst1)]
