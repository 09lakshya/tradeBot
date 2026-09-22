"""Pure functional risk rules for pre-trade risk evaluation.

Every rule is a deterministic, side-effect-free function:
evaluate(order, snapshot) -> RuleResult
"""
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domains.risk.enums import BreakerState, RiskDecision, RuleType
from app.domains.risk.snapshot import RiskSnapshot
from app.domains.trading.enums import OrderSide, OrderType


@dataclass(frozen=True)
class OrderRiskContext:
    """Context of the proposed order being evaluated."""
    order_id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal
    stop_loss: Decimal | None = None


@dataclass(frozen=True)
class RuleResult:
    """Result emitted by a single risk rule evaluation."""
    rule: RuleType
    decision: RiskDecision
    observed_value: str
    threshold_value: str
    detail: str


class RiskRule(Protocol):
    """Protocol for pure functional risk rules."""
    rule_type: RuleType

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        ...


class SanityRule:
    """Rule 1: Structural validity of the order (qty > 0, price > 0)."""
    rule_type = RuleType.sanity

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if order.quantity <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=str(order.quantity),
                threshold_value="> 0.0000",
                detail="Order quantity must be strictly positive.",
            )

        if order.price <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=str(order.price),
                threshold_value="> 0.0000",
                detail="Order price must be strictly positive.",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"qty={order.quantity}, price={order.price}",
            threshold_value="valid",
            detail="Order passed structural sanity check.",
        )


class KillSwitchRule:
    """Rule 2: Emergency master stop check."""
    rule_type = RuleType.kill_switch

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if snapshot.is_kill_switch_active:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value="active",
                threshold_value="inactive",
                detail=f"Kill switch active: {snapshot.kill_switch_reason or 'Emergency stop'}",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value="inactive",
            threshold_value="inactive",
            detail="Kill switch is inactive.",
        )


class CircuitBreakerRule:
    """Rule 3: Automatic cooloff halts for volatility or soft limits."""
    rule_type = RuleType.circuit_breaker

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        for breaker in snapshot.active_breakers:
            if breaker.state == BreakerState.tripped:
                if breaker.cooloff_until and snapshot.timestamp < breaker.cooloff_until:
                    return RuleResult(
                        rule=self.rule_type,
                        decision=RiskDecision.blocked,
                        observed_value=f"tripped until {breaker.cooloff_until.isoformat()}",
                        threshold_value="armed",
                        detail=f"Circuit breaker tripped for {breaker.scope.value}: {breaker.reason}",
                    )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value="armed",
            threshold_value="armed",
            detail="All circuit breakers normal.",
        )


class BuyingPowerRule:
    """Rule 4: Available cash and buying power sufficiency."""
    rule_type = RuleType.buying_power

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if order.side == OrderSide.buy:
            estimated_notional = (order.quantity * order.price).quantize(Decimal("0.0001"))
            total_required = estimated_notional

            if total_required > snapshot.available_buying_power:
                return RuleResult(
                    rule=self.rule_type,
                    decision=RiskDecision.blocked,
                    observed_value=f"req=₹{total_required}",
                    threshold_value=f"avail=₹{snapshot.available_buying_power}",
                    detail=f"Insufficient buying power: required ₹{total_required}, available ₹{snapshot.available_buying_power}",
                )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"avail=₹{snapshot.available_buying_power}",
            threshold_value="sufficient",
            detail="Buying power verified.",
        )


class PositionSizingRule:
    """Rule 5: Per-trade risk budget and notional cap."""
    rule_type = RuleType.position_sizing

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        order_notional = (order.quantity * order.price).quantize(Decimal("0.0001"))

        # Check maximum absolute notional cap if configured
        if snapshot.limits.max_order_notional is not None:
            if order_notional > snapshot.limits.max_order_notional:
                return RuleResult(
                    rule=self.rule_type,
                    decision=RiskDecision.blocked,
                    observed_value=f"₹{order_notional}",
                    threshold_value=f"₹{snapshot.limits.max_order_notional}",
                    detail=f"Order notional ₹{order_notional} exceeds maximum permitted ₹{snapshot.limits.max_order_notional}",
                )

        # Check risk-per-trade stop loss distance if stop_loss and per_trade_risk_pct provided
        if (
            order.stop_loss is not None
            and snapshot.current_equity > Decimal("0.0000")
            and snapshot.limits.per_trade_risk_pct is not None
        ):
            price_risk_per_share = abs(order.price - order.stop_loss)
            total_risk_amount = (price_risk_per_share * order.quantity).quantize(Decimal("0.0001"))
            max_allowed_risk = (snapshot.current_equity * snapshot.limits.per_trade_risk_pct).quantize(Decimal("0.0001"))

            if total_risk_amount > max_allowed_risk:
                return RuleResult(
                    rule=self.rule_type,
                    decision=RiskDecision.blocked,
                    observed_value=f"risk=₹{total_risk_amount}",
                    threshold_value=f"max_risk=₹{max_allowed_risk} ({snapshot.limits.per_trade_risk_pct * 100}%)",
                    detail=f"Trade risk ₹{total_risk_amount} exceeds maximum risk budget ₹{max_allowed_risk}",
                )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"notional=₹{order_notional}",
            threshold_value="within_limits",
            detail="Position sizing verified.",
        )


class ExposureLimitRule:
    """Rule 6: Instrument, sector, and maximum open position count caps."""
    rule_type = RuleType.exposure_limit

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if snapshot.current_equity <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value="equity <= 0",
                threshold_value="equity > 0",
                detail="Cannot take exposure with zero or negative portfolio equity.",
            )

        order_notional = (order.quantity * order.price).quantize(Decimal("0.0001"))

        # 1. Max open positions count check
        is_new_instrument = order.instrument_id not in snapshot.open_positions
        if is_new_instrument and order.side == OrderSide.buy:
            if len(snapshot.open_positions) >= snapshot.limits.max_open_positions:
                return RuleResult(
                    rule=self.rule_type,
                    decision=RiskDecision.blocked,
                    observed_value=f"{len(snapshot.open_positions) + 1} positions",
                    threshold_value=f"max={snapshot.limits.max_open_positions}",
                    detail=f"Open positions count reaches cap of {snapshot.limits.max_open_positions}",
                )

        # 2. Per-instrument exposure limit (e.g. 10% of equity)
        existing_pos = snapshot.open_positions.get(order.instrument_id)
        existing_mv = existing_pos.market_value if existing_pos else Decimal("0.0000")
        post_order_inst_mv = existing_mv + (order_notional if order.side == OrderSide.buy else -order_notional)
        inst_exposure_pct = (abs(post_order_inst_mv) / snapshot.current_equity).quantize(Decimal("0.0001"))

        if inst_exposure_pct > snapshot.limits.max_instrument_exposure_pct:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"{inst_exposure_pct * 100:.2f}%",
                threshold_value=f"max={snapshot.limits.max_instrument_exposure_pct * 100:.2f}%",
                detail=f"Instrument exposure {inst_exposure_pct * 100:.2f}% exceeds limit {snapshot.limits.max_instrument_exposure_pct * 100:.2f}%",
            )

        # 3. Per-sector exposure limit (e.g. 30% of equity)
        sector = snapshot.sector_mappings.get(order.instrument_id, "Unknown")
        existing_sector_mv = sum(
            pos.market_value
            for pos in snapshot.open_positions.values()
            if snapshot.sector_mappings.get(pos.instrument_id) == sector
        )
        post_order_sector_mv = existing_sector_mv + (order_notional if order.side == OrderSide.buy else -order_notional)
        sector_exposure_pct = (abs(post_order_sector_mv) / snapshot.current_equity).quantize(Decimal("0.0001"))

        if sector_exposure_pct > snapshot.limits.max_sector_exposure_pct:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"{sector_exposure_pct * 100:.2f}% ({sector})",
                threshold_value=f"max={snapshot.limits.max_sector_exposure_pct * 100:.2f}%",
                detail=f"Sector '{sector}' exposure {sector_exposure_pct * 100:.2f}% exceeds limit {snapshot.limits.max_sector_exposure_pct * 100:.2f}%",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"inst={inst_exposure_pct*100:.2f}%, sector={sector_exposure_pct*100:.2f}%",
            threshold_value="within_limits",
            detail="Exposure limits verified.",
        )


class CorrelationLimitRule:
    """Rule 7: Cluster exposure cap on highly-correlated instruments (|ρ| >= 0.80)."""
    rule_type = RuleType.correlation_limit

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if not snapshot.open_positions or snapshot.current_equity <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.passed,
                observed_value="no_correlated_cluster",
                threshold_value=f"ρ < {snapshot.limits.max_position_correlation}",
                detail="Correlation check passed.",
            )

        order_notional = (order.quantity * order.price).quantize(Decimal("0.0001"))
        cluster_mv = order_notional if order.side == OrderSide.buy else Decimal("0.0000")
        correlated_symbols = []

        for inst_id, pos in snapshot.open_positions.items():
            if inst_id == order.instrument_id:
                cluster_mv += pos.market_value
                continue

            pair = (order.instrument_id, inst_id)
            rev_pair = (inst_id, order.instrument_id)
            corr = snapshot.correlations.get(pair) or snapshot.correlations.get(rev_pair)

            if corr is not None and abs(corr) >= snapshot.limits.max_position_correlation:
                cluster_mv += pos.market_value
                correlated_symbols.append(pos.symbol)

        # Max allowed cluster exposure: 2x max_instrument_exposure_pct (e.g. 20%)
        cluster_cap_pct = snapshot.limits.max_instrument_exposure_pct * Decimal("2.0")
        cluster_exposure_pct = (cluster_mv / snapshot.current_equity).quantize(Decimal("0.0001"))

        if correlated_symbols and cluster_exposure_pct > cluster_cap_pct:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"{cluster_exposure_pct * 100:.2f}% with {correlated_symbols}",
                threshold_value=f"max={cluster_cap_pct * 100:.2f}%",
                detail=f"Correlated cluster exposure {cluster_exposure_pct * 100:.2f}% exceeds {cluster_cap_pct * 100:.2f}%",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"cluster_exp={cluster_exposure_pct * 100:.2f}%",
            threshold_value=f"max={cluster_cap_pct * 100:.2f}%",
            detail="Correlation limits verified.",
        )


class DailyLossLimitRule:
    """Rule 8: Halt new risk-increasing orders when daily loss exceeds limit (e.g. 2%)."""
    rule_type = RuleType.daily_loss_limit

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if snapshot.current_equity <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value="equity <= 0",
                threshold_value="equity > 0",
                detail="Equity exhausted.",
            )

        total_today_pnl = snapshot.today_realized_pnl + snapshot.today_unrealized_pnl
        max_loss_amount = -(snapshot.current_equity * snapshot.limits.max_daily_loss_pct).quantize(Decimal("0.0001"))

        if total_today_pnl < max_loss_amount:
            # Allow position-closing orders to reduce risk
            existing_pos = snapshot.open_positions.get(order.instrument_id)
            if existing_pos and order.side == OrderSide.sell:
                return RuleResult(
                    rule=self.rule_type,
                    decision=RiskDecision.passed,
                    observed_value=f"today_pnl=₹{total_today_pnl}",
                    threshold_value="closing_permitted",
                    detail="Risk-reducing position close permitted under daily loss breach.",
                )

            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"loss=₹{abs(total_today_pnl)}",
                threshold_value=f"max_loss=₹{abs(max_loss_amount)} ({snapshot.limits.max_daily_loss_pct * 100}%)",
                detail=f"Daily loss ₹{abs(total_today_pnl)} breached cap of ₹{abs(max_loss_amount)}",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"pnl=₹{total_today_pnl}",
            threshold_value=f"loss_cap=₹{abs(max_loss_amount)}",
            detail="Daily loss within limit.",
        )


class DrawdownLimitRule:
    """Rule 9: Maximum peak-to-trough portfolio drawdown cap (e.g. 15%)."""
    rule_type = RuleType.drawdown_limit

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if snapshot.peak_equity <= Decimal("0.0000"):
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.passed,
                observed_value="0.00%",
                threshold_value=f"{snapshot.limits.max_drawdown_pct * 100}%",
                detail="Drawdown check passed.",
            )

        drawdown = ((snapshot.peak_equity - snapshot.current_equity) / snapshot.peak_equity).quantize(Decimal("0.0001"))

        if drawdown >= snapshot.limits.max_drawdown_pct:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"{drawdown * 100:.2f}%",
                threshold_value=f"max={snapshot.limits.max_drawdown_pct * 100:.2f}%",
                detail=f"Portfolio drawdown {drawdown * 100:.2f}% breached maximum allowed {snapshot.limits.max_drawdown_pct * 100:.2f}%",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"{drawdown * 100:.2f}%",
            threshold_value=f"max={snapshot.limits.max_drawdown_pct * 100:.2f}%",
            detail="Drawdown within limit.",
        )


class RateLimitRule:
    """Rule 10: Order frequency rate limits and anti-thrashing."""
    rule_type = RuleType.rate_limit

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RuleResult:
        if snapshot.recent_order_count >= snapshot.limits.max_orders_per_minute:
            return RuleResult(
                rule=self.rule_type,
                decision=RiskDecision.blocked,
                observed_value=f"{snapshot.recent_order_count} orders/min",
                threshold_value=f"max={snapshot.limits.max_orders_per_minute} orders/min",
                detail="Order velocity rate limit exceeded.",
            )

        return RuleResult(
            rule=self.rule_type,
            decision=RiskDecision.passed,
            observed_value=f"{snapshot.recent_order_count} orders/min",
            threshold_value=f"max={snapshot.limits.max_orders_per_minute}",
            detail="Rate limit normal.",
        )
