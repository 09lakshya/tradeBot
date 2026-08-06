"""Unit tests verifying deterministic execution and replay parity in Portfolio Construction."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.schemas import PortfolioConstructionConfig, PortfolioSnapshot
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import FixedClock


def test_deterministic_candidate_order_parity():
    """Identical signals and portfolio state must produce bit-for-bit identical candidate allocations."""
    eval_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    clock1 = FixedClock(eval_time)
    clock2 = FixedClock(eval_time)

    service1 = PortfolioConstructionService(clock=clock1)
    service2 = PortfolioConstructionService(clock=clock2)

    portfolio_id = uuid.uuid4()
    inst_a = uuid.uuid4()
    inst_b = uuid.uuid4()

    sig1 = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="strat_trend",
        instrument_id=inst_a,
        symbol="STOCK_A",
        timestamp=eval_time,
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=0.88,
        entry_price=Decimal("150.00"),
    )
    sig2 = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="strat_mom",
        instrument_id=inst_b,
        symbol="STOCK_B",
        timestamp=eval_time,
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=0.74,
        entry_price=Decimal("300.00"),
    )

    snapshot = PortfolioSnapshot(
        portfolio_id=portfolio_id,
        timestamp=eval_time,
        cash_balance=Decimal("200000.00"),
        total_equity=Decimal("200000.00"),
    )

    config = PortfolioConstructionConfig()

    plan1 = service1.construct_portfolio(
        portfolio_snapshot=snapshot,
        signals=[sig1, sig2],
        config=config,
        current_prices={inst_a: Decimal("150.00"), inst_b: Decimal("300.00")},
    )

    plan2 = service2.construct_portfolio(
        portfolio_snapshot=snapshot,
        signals=[sig1, sig2],
        config=config,
        current_prices={inst_a: Decimal("150.00"), inst_b: Decimal("300.00")},
    )

    assert len(plan1.candidate_orders) == len(plan2.candidate_orders)
    for c1, c2 in zip(plan1.candidate_orders, plan2.candidate_orders):
        assert c1.symbol == c2.symbol
        assert c1.quantity == c2.quantity
        assert c1.target_weight == c2.target_weight
        assert c1.estimated_notional == c2.estimated_notional
        assert c1.ranking_score == c2.ranking_score
