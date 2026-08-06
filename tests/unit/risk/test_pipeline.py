"""Unit tests for the pre-trade risk evaluation pipeline and fail-closed semantics."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest

from app.domains.risk.enums import RiskDecision
from app.domains.risk.models import RiskLimit
from app.domains.risk.pipeline import RiskPipeline
from app.domains.risk.rules import OrderRiskContext, RiskRule, RuleResult
from app.domains.risk.snapshot import RiskSnapshot
from app.domains.trading.enums import OrderSide, OrderType


@pytest.fixture
def base_snapshot():
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    limits = RiskLimit(
        portfolio_id=uuid.uuid4(),
        max_daily_loss_pct=Decimal("0.0200"),
        max_drawdown_pct=Decimal("0.1500"),
        per_trade_risk_pct=Decimal("0.0100"),
        max_portfolio_heat_pct=Decimal("0.0600"),
        max_open_positions=10,
        max_instrument_exposure_pct=Decimal("0.1000"),
        max_sector_exposure_pct=Decimal("0.3000"),
        max_position_correlation=Decimal("0.8000"),
        max_order_notional=Decimal("50000.0000"),
        max_orders_per_minute=30,
        is_active=True,
    )
    return RiskSnapshot(
        portfolio_id=limits.portfolio_id,
        cash_balance=Decimal("100000.0000"),
        reserved_cash=Decimal("0.0000"),
        available_buying_power=Decimal("100000.0000"),
        current_equity=Decimal("100000.0000"),
        peak_equity=Decimal("100000.0000"),
        today_realized_pnl=Decimal("0.0000"),
        today_unrealized_pnl=Decimal("0.0000"),
        open_positions={},
        recent_order_count=0,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(),
        volatilities={},
        correlations={},
        sector_mappings={},
        limits=limits,
        timestamp=now,
    )


def test_pipeline_all_pass_returns_valid_token(base_snapshot):
    pipeline = RiskPipeline()
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=uuid.uuid4(),
        symbol="TCS",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("2.0000"),
        price=Decimal("3500.0000"),  # ₹7,000 <= 10%
    )

    verdict = pipeline.evaluate(order, base_snapshot)
    assert verdict.decision == RiskDecision.passed
    assert verdict.blocking_rule is None
    assert len(verdict.verdict_token) == 64  # SHA256 hex string
    assert len(verdict.rule_results) == 10  # All 10 rules evaluated and passed


def test_pipeline_short_circuits_on_block(base_snapshot):
    pipeline = RiskPipeline()
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=uuid.uuid4(),
        symbol="TCS",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("-5.0000"),  # Fails rule 1 (sanity)
        price=Decimal("3500.0000"),
    )

    verdict = pipeline.evaluate(order, base_snapshot)
    assert verdict.decision == RiskDecision.blocked
    assert verdict.blocking_rule == "sanity"
    assert len(verdict.rule_results) == 1  # Short-circuited after rule 1


class FaultyCrashingRule:
    """Mock rule that raises unexpected runtime exception."""
    rule_type = "faulty_rule"

    def evaluate(self, order, snapshot):
        raise RuntimeError("Simulated internal algorithmic crash!")


def test_pipeline_fail_closed_guarantee(base_snapshot):
    """Verifies that an internal exception NEVER passes an order silently (fail-closed)."""
    pipeline = RiskPipeline(rules=[FaultyCrashingRule()])
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=uuid.uuid4(),
        symbol="INFY",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("1.0000"),
        price=Decimal("1500.0000"),
    )

    verdict = pipeline.evaluate(order, base_snapshot)
    assert verdict.decision == RiskDecision.blocked
    assert verdict.blocking_rule == "pipeline_fail_closed"
    assert "Simulated internal algorithmic crash" in verdict.reason
