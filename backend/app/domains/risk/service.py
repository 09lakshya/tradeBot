"""Risk Service orchestrating snapshot creation, rule evaluation, and audit persistence."""
from datetime import datetime
from decimal import Decimal
import logging
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.market_data.models import Instrument
from app.domains.risk.circuit_breaker import CircuitBreakerManager, KillSwitchManager
from app.domains.risk.enums import RiskDecision, ScopeType
from app.domains.risk.exceptions import RiskLimitsNotFoundError
from app.domains.risk.models import CircuitBreaker, KillSwitch, RiskEvent, RiskLimit
from app.domains.risk.pipeline import RiskPipeline
from app.domains.risk.rules import OrderRiskContext
from app.domains.risk.schemas import (
    RiskLimitUpdate,
    RiskStatusSummary,
    RiskVerdict,
)
from app.domains.risk.snapshot import RiskSnapshotBuilder
from app.domains.trading.clock import Clock
from app.domains.trading.models import Order

log = logging.getLogger(__name__)


class RiskService:
    """Core domain service for pre-trade risk evaluation, limits management, and audit trails."""

    def __init__(
        self,
        clock: Clock,
        pipeline: RiskPipeline | None = None,
    ):
        self.clock = clock
        self.pipeline = pipeline or RiskPipeline()

    def evaluate_order(
        self,
        db: Session,
        order: Order,
        market_prices: dict[uuid.UUID, Decimal] | None = None,
        volatilities: dict[uuid.UUID, Decimal] | None = None,
        correlations: dict[tuple[uuid.UUID, uuid.UUID], Decimal] | None = None,
    ) -> RiskVerdict:
        """Mandatory pre-trade gate: evaluates order against all rules and records audit events."""
        builder = RiskSnapshotBuilder(db=db, clock=self.clock)
        snapshot = builder.build_snapshot(
            portfolio_id=order.portfolio_id,
            market_prices=market_prices,
            volatilities=volatilities,
            correlations=correlations,
        )

        inst = db.get(Instrument, order.instrument_id)
        symbol = inst.trading_symbol if inst else str(order.instrument_id)

        eff_price = order.limit_price or order.avg_fill_price or (
            market_prices.get(order.instrument_id) if market_prices else None
        ) or Decimal("1000.0000")

        order_context = OrderRiskContext(
            order_id=order.id,
            portfolio_id=order.portfolio_id,
            instrument_id=order.instrument_id,
            symbol=symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=eff_price,
            stop_loss=order.stop_price,
        )

        verdict: RiskVerdict = self.pipeline.evaluate(order_context, snapshot)

        # Persist audit trail of rule evaluations to DB
        for res in verdict.rule_results:
            event = RiskEvent(
                portfolio_id=order.portfolio_id,
                order_id=order.id,
                rule=res.rule,
                decision=res.decision,
                observed_value=res.observed_value,
                threshold_value=res.threshold_value,
                detail=res.detail,
            )
            db.add(event)

        db.flush()
        return verdict

    def get_or_create_limits(self, db: Session, portfolio_id: uuid.UUID) -> RiskLimit:
        """Fetch active risk limits or create standard conservative defaults."""
        limits = db.execute(
            select(RiskLimit).where(RiskLimit.portfolio_id == portfolio_id)
        ).scalar_one_or_none()

        if not limits:
            limits = RiskLimit(portfolio_id=portfolio_id)
            db.add(limits)
            db.flush()

        return limits

    def update_limits(
        self, db: Session, portfolio_id: uuid.UUID, updates: RiskLimitUpdate
    ) -> RiskLimit:
        """Update configurable risk limits for a portfolio."""
        limits = self.get_or_create_limits(db, portfolio_id)

        for field, value in updates.model_dump(exclude_unset=True).items():
            setattr(limits, field, value)

        db.flush()
        return limits

    def trip_kill_switch(
        self,
        db: Session,
        scope: ScopeType,
        scope_id: str | None,
        reason: str,
        activated_by: str = "user",
    ) -> KillSwitch:
        """Activate emergency stop."""
        ks_mgr = KillSwitchManager(db=db, clock=self.clock)
        return ks_mgr.trip(
            scope=scope,
            scope_id=scope_id,
            reason=reason,
            activated_by=activated_by,
        )

    def reset_kill_switch(
        self,
        db: Session,
        scope: ScopeType,
        scope_id: str | None,
        reset_reason: str,
        reset_by: str = "user",
    ) -> KillSwitch | None:
        """Reset emergency stop (audited)."""
        ks_mgr = KillSwitchManager(db=db, clock=self.clock)
        return ks_mgr.reset(
            scope=scope,
            scope_id=scope_id,
            reset_reason=reset_reason,
            reset_by=reset_by,
        )

    def trip_circuit_breaker(
        self,
        db: Session,
        scope: ScopeType,
        scope_id: str | None,
        reason: str,
        cooloff_seconds: int = 300,
    ) -> CircuitBreaker:
        """Trip circuit breaker for automatic cooldown."""
        cb_mgr = CircuitBreakerManager(db=db, clock=self.clock)
        return cb_mgr.trip(
            scope=scope,
            scope_id=scope_id,
            reason=reason,
            cooloff_seconds=cooloff_seconds,
        )

    def get_risk_status(self, db: Session, portfolio_id: uuid.UUID) -> RiskStatusSummary:
        """Compute real-time risk health summary for a portfolio."""
        builder = RiskSnapshotBuilder(db=db, clock=self.clock)
        snapshot = builder.build_snapshot(portfolio_id=portfolio_id)

        drawdown = (
            ((snapshot.peak_equity - snapshot.current_equity) / snapshot.peak_equity).quantize(Decimal("0.0001"))
            if snapshot.peak_equity > Decimal("0.0000")
            else Decimal("0.0000")
        )

        gross_exposure = sum((pos.market_value for pos in snapshot.open_positions.values()), Decimal("0.0000"))
        net_exposure = sum(
            (
                pos.market_value if pos.quantity > Decimal("0.0000") else -pos.market_value
                for pos in snapshot.open_positions.values()
            ),
            Decimal("0.0000"),
        )

        return RiskStatusSummary(
            portfolio_id=portfolio_id,
            current_equity=snapshot.current_equity,
            peak_equity=snapshot.peak_equity,
            current_drawdown_pct=drawdown,
            today_realized_pnl=snapshot.today_realized_pnl,
            today_unrealized_pnl=snapshot.today_unrealized_pnl,
            open_positions_count=len(snapshot.open_positions),
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            kill_switch_active=snapshot.is_kill_switch_active,
            active_circuit_breakers_count=len(snapshot.active_breakers),
            timestamp=snapshot.timestamp,
        )
