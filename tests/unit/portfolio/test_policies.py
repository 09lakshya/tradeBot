"""Unit tests for Portfolio Allocation Policies."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.enums import AllocationPolicyType, ArbitrationMethod
from app.domains.portfolio.policies import (
    AllocationPolicyRegistry,
    EqualWeightPolicy,
    ScoreProportionalPolicy,
    VolatilityInversePolicy,
)
from app.domains.portfolio.schemas import ArbitrationDecision, PortfolioSnapshot, SignalRankingScore
from app.domains.strategies.enums import SignalDirection
from app.domains.trading.enums import OrderSide


def create_decision(inst_id: uuid.UUID, symbol: str, sig_id: uuid.UUID) -> ArbitrationDecision:
    return ArbitrationDecision(
        instrument_id=inst_id,
        symbol=symbol,
        winning_side=OrderSide.buy,
        selected_signals=[sig_id],
        discarded_signals=[],
        blended_confidence=0.8,
        blended_entry_price=Decimal("100.00"),
        blended_stop_loss=Decimal("95.00"),
        blended_take_profit=Decimal("110.00"),
        conflict_type="NO_CONFLICT",
        resolution_method=ArbitrationMethod.net_confidence_weighted,
        reason="Test",
    )


def test_equal_weight_policy():
    policy = EqualWeightPolicy()
    id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    decisions = [
        create_decision(id1, "A", uuid.uuid4()),
        create_decision(id2, "B", uuid.uuid4()),
        create_decision(id3, "C", uuid.uuid4()),
    ]
    snap = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
    )

    budget = Decimal("0.9000")
    weights = policy.compute_target_weights(decisions, snap, {}, budget)
    assert len(weights) == 3
    assert weights[id1] == Decimal("0.3000")
    assert weights[id2] == Decimal("0.3000")
    assert weights[id3] == Decimal("0.3000")


def test_volatility_inverse_policy():
    policy = VolatilityInversePolicy()
    id_low_vol = uuid.uuid4()
    id_high_vol = uuid.uuid4()

    decisions = [
        create_decision(id_low_vol, "LOW", uuid.uuid4()),
        create_decision(id_high_vol, "HIGH", uuid.uuid4()),
    ]

    snap = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
        volatilities={
            id_low_vol: Decimal("0.1000"),   # Inv vol = 10
            id_high_vol: Decimal("0.2000"),  # Inv vol = 5
        },
    )

    budget = Decimal("0.9000")
    weights = policy.compute_target_weights(decisions, snap, {}, budget)

    # 10 / 15 * 0.9 = 0.60, 5 / 15 * 0.9 = 0.30
    assert weights[id_low_vol] == Decimal("0.6000")
    assert weights[id_high_vol] == Decimal("0.3000")


def test_score_proportional_policy():
    policy = ScoreProportionalPolicy()
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    sig1_id = uuid.uuid4()
    sig2_id = uuid.uuid4()

    decisions = [
        create_decision(id1, "A", sig1_id),
        create_decision(id2, "B", sig2_id),
    ]

    ranking_scores = {
        sig1_id: SignalRankingScore(
            signal_id=sig1_id,
            instrument_id=id1,
            symbol="A",
            strategy_id="strat",
            direction=SignalDirection.long,
            composite_score=0.75,
            rank=1,
            explanation="",
        ),
        sig2_id: SignalRankingScore(
            signal_id=sig2_id,
            instrument_id=id2,
            symbol="B",
            strategy_id="strat",
            direction=SignalDirection.long,
            composite_score=0.25,
            rank=2,
            explanation="",
        ),
    }

    snap = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("100000"),
        total_equity=Decimal("100000"),
    )

    budget = Decimal("1.0000")
    weights = policy.compute_target_weights(decisions, snap, ranking_scores, budget)
    assert weights[id1] == Decimal("0.7500")
    assert weights[id2] == Decimal("0.2500")
