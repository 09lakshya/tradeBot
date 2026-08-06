"""Unit tests for PositionSizingEngine."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.enums import ArbitrationMethod, SizingMethod
from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    PortfolioConstructionConfig,
    PortfolioSnapshot,
    SignalRankingScore,
)
from app.domains.portfolio.sizing import PositionSizingEngine
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.enums import OrderSide


def create_signal(inst_id: uuid.UUID, symbol: str) -> TradingSignal:
    return TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="momentum_strategy",
        instrument_id=inst_id,
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=0.85,
        expected_return=Decimal("0.0500"),
        expected_risk=Decimal("0.0200"),
        risk_reward_ratio=Decimal("2.5"),
    )


def test_fixed_fractional_sizing():
    engine = PositionSizingEngine()
    inst = uuid.uuid4()
    sig = create_signal(inst, "RELIANCE")
    plan_id = uuid.uuid4()

    decision = ArbitrationDecision(
        instrument_id=inst,
        symbol="RELIANCE",
        winning_side=OrderSide.buy,
        selected_signals=[sig.signal_id],
        discarded_signals=[],
        blended_confidence=0.85,
        blended_entry_price=Decimal("2500.00"),
        blended_stop_loss=Decimal("2400.00"),
        blended_take_profit=Decimal("2750.00"),
        conflict_type="NO_CONFLICT",
        resolution_method=ArbitrationMethod.net_confidence_weighted,
        reason="Test",
    )

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("1000000.00"),
        total_equity=Decimal("1000000.00"),
    )

    # 10% target weight -> 100,000 INR / 2,500 = 40 shares
    config = PortfolioConstructionConfig(sizing_method=SizingMethod.fixed_fractional)
    orders = engine.size_positions(
        plan_id=plan_id,
        decisions={inst: decision},
        target_weights={inst: Decimal("0.1000")},
        snapshot=snapshot,
        signals_map={inst: [sig]},
        ranking_scores={},
        config=config,
        current_prices={inst: Decimal("2500.00")},
    )

    assert len(orders) == 1
    ord0 = orders[0]
    assert ord0.quantity == Decimal("40")
    assert ord0.estimated_notional == Decimal("100000.0000")
    assert ord0.transaction_costs.total_estimated_costs > Decimal("0")
    assert ord0.side == OrderSide.buy


def test_atr_risk_per_trade_sizing():
    engine = PositionSizingEngine()
    inst = uuid.uuid4()
    sig = create_signal(inst, "INFY")
    plan_id = uuid.uuid4()

    # Price 1500, Stop Loss 1450 (stop distance = 50)
    decision = ArbitrationDecision(
        instrument_id=inst,
        symbol="INFY",
        winning_side=OrderSide.buy,
        selected_signals=[sig.signal_id],
        discarded_signals=[],
        blended_confidence=0.90,
        blended_entry_price=Decimal("1500.00"),
        blended_stop_loss=Decimal("1450.00"),
        blended_take_profit=Decimal("1600.00"),
        conflict_type="NO_CONFLICT",
        resolution_method=ArbitrationMethod.net_confidence_weighted,
        reason="Test",
    )

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        cash_balance=Decimal("500000.00"),
        total_equity=Decimal("500000.00"),
    )

    # 1% risk per trade -> 5,000 INR risk budget / 50 stop dist = 100 shares
    # Target notional cap: 500,000 * 0.40 = 200,000 INR -> 133 shares cap
    # Therefore 100 shares selected
    config = PortfolioConstructionConfig(
        sizing_method=SizingMethod.atr_risk_per_trade,
        risk_per_trade_pct=Decimal("0.0100"),
    )

    orders = engine.size_positions(
        plan_id=plan_id,
        decisions={inst: decision},
        target_weights={inst: Decimal("0.4000")},
        snapshot=snapshot,
        signals_map={inst: [sig]},
        ranking_scores={},
        config=config,
        current_prices={inst: Decimal("1500.00")},
    )

    assert len(orders) == 1
    assert orders[0].quantity == Decimal("100")
    assert orders[0].estimated_notional == Decimal("150000.0000")
