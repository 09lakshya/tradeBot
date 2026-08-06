"""Unit tests for all 10 pure functional pre-trade risk rules."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest

from app.domains.risk.enums import BreakerState, RiskDecision, RuleType, ScopeType
from app.domains.risk.models import RiskLimit
from app.domains.risk.rules import (
    BuyingPowerRule,
    CircuitBreakerRule,
    CorrelationLimitRule,
    DailyLossLimitRule,
    DrawdownLimitRule,
    ExposureLimitRule,
    KillSwitchRule,
    OrderRiskContext,
    PositionSizingRule,
    RateLimitRule,
    SanityRule,
)
from app.domains.risk.snapshot import BreakerSnapshot, PositionRiskSnapshot, RiskSnapshot
from app.domains.trading.enums import OrderSide, OrderType


@pytest.fixture
def base_limits():
    return RiskLimit(
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


@pytest.fixture
def base_snapshot(base_limits):
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    return RiskSnapshot(
        portfolio_id=base_limits.portfolio_id,
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
        limits=base_limits,
        timestamp=now,
    )


def test_rule_1_sanity_checks(base_snapshot):
    rule = SanityRule()
    inst_id = uuid.uuid4()

    # Valid order
    order_ok = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("10.0000"),
        price=Decimal("2500.0000"),
    )
    res = rule.evaluate(order_ok, base_snapshot)
    assert res.decision == RiskDecision.passed

    # Zero or negative quantity
    order_zero_qty = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("0.0000"),
        price=Decimal("2500.0000"),
    )
    res_zero = rule.evaluate(order_zero_qty, base_snapshot)
    assert res_zero.decision == RiskDecision.blocked
    assert "quantity" in res_zero.detail.lower()

    # Zero or negative price
    order_neg_price = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("10.0000"),
        price=Decimal("-10.0000"),
    )
    res_neg_p = rule.evaluate(order_neg_price, base_snapshot)
    assert res_neg_p.decision == RiskDecision.blocked
    assert "price" in res_neg_p.detail.lower()


def test_rule_2_kill_switch(base_snapshot, base_limits):
    rule = KillSwitchRule()
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=uuid.uuid4(),
        symbol="TCS",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("5.0000"),
        price=Decimal("3500.0000"),
    )

    # Inactive kill switch -> Pass
    res = rule.evaluate(order, base_snapshot)
    assert res.decision == RiskDecision.passed

    # Active kill switch -> Block
    ks_active_snap = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=base_snapshot.today_realized_pnl,
        today_unrealized_pnl=base_snapshot.today_unrealized_pnl,
        open_positions={},
        recent_order_count=0,
        is_kill_switch_active=True,
        kill_switch_reason="Manual emergency halt",
        active_breakers=(),
        volatilities={},
        correlations={},
        sector_mappings={},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )
    res_blocked = rule.evaluate(order, ks_active_snap)
    assert res_blocked.decision == RiskDecision.blocked
    assert "Kill switch active" in res_blocked.detail


def test_rule_3_circuit_breaker(base_snapshot, base_limits):
    rule = CircuitBreakerRule()
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=uuid.uuid4(),
        symbol="INFY",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("10.0000"),
        price=Decimal("1500.0000"),
    )

    # No active breakers -> Pass
    res = rule.evaluate(order, base_snapshot)
    assert res.decision == RiskDecision.passed

    # Active breaker in cooldown -> Block
    cooloff = base_snapshot.timestamp + timedelta(minutes=5)
    cb_snap = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=base_snapshot.today_realized_pnl,
        today_unrealized_pnl=base_snapshot.today_unrealized_pnl,
        open_positions={},
        recent_order_count=0,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(
            BreakerSnapshot(
                scope=ScopeType.portfolio,
                scope_id=str(base_snapshot.portfolio_id),
                state=BreakerState.tripped,
                cooloff_until=cooloff,
                reason="Excessive intraday volatility",
            ),
        ),
        volatilities={},
        correlations={},
        sector_mappings={},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )
    res_cb = rule.evaluate(order, cb_snap)
    assert res_cb.decision == RiskDecision.blocked
    assert "Circuit breaker tripped" in res_cb.detail


def test_rule_4_buying_power(base_snapshot):
    rule = BuyingPowerRule()
    inst_id = uuid.uuid4()

    # Order notional + buffer <= available buying power (₹100,000)
    order_ok = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="HDFCBANK",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("50.0000"),
        price=Decimal("1500.0000"),  # ₹75,000 notional
    )
    res_ok = rule.evaluate(order_ok, base_snapshot)
    assert res_ok.decision == RiskDecision.passed

    # Order exceeding buying power
    order_excess = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="HDFCBANK",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        price=Decimal("1500.0000"),  # ₹150,000 notional > ₹100,000
    )
    res_excess = rule.evaluate(order_excess, base_snapshot)
    assert res_excess.decision == RiskDecision.blocked
    assert "Insufficient buying power" in res_excess.detail


def test_rule_5_position_sizing_and_notional_cap(base_snapshot):
    rule = PositionSizingRule()
    inst_id = uuid.uuid4()

    # Order within ₹50,000 max_order_notional
    order_ok = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="SBIN",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("50.0000"),
        price=Decimal("600.0000"),  # ₹30,000 notional
        stop_loss=Decimal("590.0000"),  # Risk = 50 * 10 = ₹500 <= 1% of ₹100k (₹1000)
    )
    res_ok = rule.evaluate(order_ok, base_snapshot)
    assert res_ok.decision == RiskDecision.passed

    # Order exceeding max notional cap (₹60,000 > ₹50,000)
    order_excess_notional = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="SBIN",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("100.0000"),
        price=Decimal("600.0000"),  # ₹60,000 notional
    )
    res_excess_notional = rule.evaluate(order_excess_notional, base_snapshot)
    assert res_excess_notional.decision == RiskDecision.blocked
    assert "exceeds maximum permitted" in res_excess_notional.detail

    # Order exceeding 1% risk-per-trade stop distance
    # Equity = 100k, 1% = ₹1000. Here risk = 50 shares * (600 - 550) = ₹2500 > ₹1000
    order_excess_risk = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="SBIN",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("50.0000"),
        price=Decimal("600.0000"),
        stop_loss=Decimal("550.0000"),
    )
    res_excess_risk = rule.evaluate(order_excess_risk, base_snapshot)
    assert res_excess_risk.decision == RiskDecision.blocked
    assert "exceeds maximum risk budget" in res_excess_risk.detail


def test_rule_6_exposure_limits(base_snapshot, base_limits):
    rule = ExposureLimitRule()
    inst_id = uuid.uuid4()

    # 1. Instrument exposure: max 10% of ₹100k equity = ₹10,000
    order_ok = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="ITC",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("20.0000"),
        price=Decimal("400.0000"),  # ₹8,000 (8% <= 10%)
    )
    res_ok = rule.evaluate(order_ok, base_snapshot)
    assert res_ok.decision == RiskDecision.passed

    order_breach_inst = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="ITC",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("30.0000"),
        price=Decimal("400.0000"),  # ₹12,000 (12% > 10%)
    )
    res_breach_inst = rule.evaluate(order_breach_inst, base_snapshot)
    assert res_breach_inst.decision == RiskDecision.blocked
    assert "Instrument exposure" in res_breach_inst.detail

    # 2. Sector exposure: max 30% of ₹100k equity = ₹30,000
    pos1_id = uuid.uuid4()
    snap_with_sector = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=base_snapshot.today_realized_pnl,
        today_unrealized_pnl=base_snapshot.today_unrealized_pnl,
        open_positions={
            pos1_id: PositionRiskSnapshot(
                instrument_id=pos1_id,
                symbol="HDFCBANK",
                sector="Banking",
                quantity=Decimal("20.0000"),
                average_entry_price=Decimal("1400.0000"),
                current_market_price=Decimal("1400.0000"),
                market_value=Decimal("28000.0000"),  # ₹28,000 in Banking
                unrealized_pnl=Decimal("0.0000"),
                realized_pnl=Decimal("0.0000"),
            )
        },
        recent_order_count=0,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(),
        volatilities={},
        correlations={},
        sector_mappings={pos1_id: "Banking", inst_id: "Banking"},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )

    # Adding ₹5,000 in Banking makes total Banking ₹33,000 > ₹30,000 (33% > 30%)
    order_banking = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="ICICIBANK",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("5.0000"),
        price=Decimal("1000.0000"),  # ₹5,000
    )
    res_sector_breach = rule.evaluate(order_banking, snap_with_sector)
    assert res_sector_breach.decision == RiskDecision.blocked
    assert "Sector 'Banking' exposure" in res_sector_breach.detail


def test_rule_7_correlation_limits(base_snapshot, base_limits):
    rule = CorrelationLimitRule()
    inst_a = uuid.uuid4()
    inst_b = uuid.uuid4()

    # Setup open position in inst_a with ₹15,000 market value
    snap_corr = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=base_snapshot.today_realized_pnl,
        today_unrealized_pnl=base_snapshot.today_unrealized_pnl,
        open_positions={
            inst_a: PositionRiskSnapshot(
                instrument_id=inst_a,
                symbol="TCS",
                sector="IT",
                quantity=Decimal("5.0000"),
                average_entry_price=Decimal("3000.0000"),
                current_market_price=Decimal("3000.0000"),
                market_value=Decimal("15000.0000"),
                unrealized_pnl=Decimal("0.0000"),
                realized_pnl=Decimal("0.0000"),
            )
        },
        recent_order_count=0,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(),
        volatilities={},
        correlations={(inst_b, inst_a): Decimal("0.9200")},  # High correlation 0.92 >= 0.80
        sector_mappings={},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )

    # Order in inst_b for ₹8,000 -> cluster becomes ₹23,000 > 2x 10% (₹20,000)
    order_b = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_b,
        symbol="INFY",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("5.0000"),
        price=Decimal("1600.0000"),  # ₹8,000
    )
    res_corr = rule.evaluate(order_b, snap_corr)
    assert res_corr.decision == RiskDecision.blocked
    assert "Correlated cluster exposure" in res_corr.detail


def test_rule_8_daily_loss_limit(base_snapshot, base_limits):
    rule = DailyLossLimitRule()
    inst_id = uuid.uuid4()

    # Normal day (no loss) -> Pass
    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("1.0000"),
        price=Decimal("2500.0000"),
    )
    res_ok = rule.evaluate(order, base_snapshot)
    assert res_ok.decision == RiskDecision.passed

    # Daily loss = -₹2,500 on ₹100,000 equity (2.5% loss > 2% max_daily_loss_pct)
    loss_snap = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=Decimal("-1500.0000"),
        today_unrealized_pnl=Decimal("-1000.0000"),
        open_positions={},
        recent_order_count=0,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(),
        volatilities={},
        correlations={},
        sector_mappings={},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )
    res_loss = rule.evaluate(order, loss_snap)
    assert res_loss.decision == RiskDecision.blocked
    assert "Daily loss" in res_loss.detail


def test_rule_9_drawdown_limit(base_snapshot, base_limits):
    rule = DrawdownLimitRule()
    inst_id = uuid.uuid4()

    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("1.0000"),
        price=Decimal("2500.0000"),
    )

    # Drawdown = (100k - 80k) / 100k = 20% > 15% max_drawdown_pct
    dd_snap = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=Decimal("80000.0000"),
        reserved_cash=Decimal("0.0000"),
        available_buying_power=Decimal("80000.0000"),
        current_equity=Decimal("80000.0000"),
        peak_equity=Decimal("100000.0000"),  # Peak was 100k
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
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )
    res_dd = rule.evaluate(order, dd_snap)
    assert res_dd.decision == RiskDecision.blocked
    assert "Portfolio drawdown" in res_dd.detail


def test_rule_10_rate_limit(base_snapshot, base_limits):
    rule = RateLimitRule()
    inst_id = uuid.uuid4()

    order = OrderRiskContext(
        order_id=uuid.uuid4(),
        portfolio_id=base_snapshot.portfolio_id,
        instrument_id=inst_id,
        symbol="RELIANCE",
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("1.0000"),
        price=Decimal("2500.0000"),
    )

    # 35 orders in last minute > 30 max_orders_per_minute
    rate_snap = RiskSnapshot(
        portfolio_id=base_snapshot.portfolio_id,
        cash_balance=base_snapshot.cash_balance,
        reserved_cash=base_snapshot.reserved_cash,
        available_buying_power=base_snapshot.available_buying_power,
        current_equity=base_snapshot.current_equity,
        peak_equity=base_snapshot.peak_equity,
        today_realized_pnl=Decimal("0.0000"),
        today_unrealized_pnl=Decimal("0.0000"),
        open_positions={},
        recent_order_count=35,
        is_kill_switch_active=False,
        kill_switch_reason=None,
        active_breakers=(),
        volatilities={},
        correlations={},
        sector_mappings={},
        limits=base_limits,
        timestamp=base_snapshot.timestamp,
    )
    res_rate = rule.evaluate(order, rate_snap)
    assert res_rate.decision == RiskDecision.blocked
    assert "Order velocity rate limit exceeded" in res_rate.detail
