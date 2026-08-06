"""Stateless execution pipeline coordinator executing the multi-stage trading cycle with complete production observability."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import time
from typing import Any, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.market_data.models import Instrument
from app.domains.orchestrator.enums import CycleStatus, OrchestratorMode, PipelineStage
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.events import (
    MarketDataUpdatedEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioConstructionCompletedEvent,
    PortfolioUpdatedEvent,
    RiskEvaluationCompletedEvent,
    StrategyEvaluationCompletedEvent,
)
from app.domains.orchestrator.exceptions import MarketClosedError, PipelineExecutionError
from app.domains.orchestrator.invariants import InvariantValidator
from app.domains.orchestrator.metrics import ContinuousMetricsTracker
from app.domains.orchestrator.models import ExecutionCycleRecord
from app.domains.orchestrator.schemas import ExecutionCycleResult
from app.domains.orchestrator.session_manager import MarketSessionManager
from app.domains.platform.audit import AuditTrailService
from app.domains.platform.circuit_breaker import global_circuit_breaker_registry
from app.domains.platform.logging import (
    get_structured_logger,
    log_context,
)
from app.domains.platform.profiler import global_performance_profiler
from app.domains.platform.tracing import (
    SpanKind,
    trace_span,
)
from app.domains.portfolio.enums import CandidateOrderStatus
from app.domains.portfolio.schemas import CandidateOrder, PortfolioConstructionConfig
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.risk.enums import RiskDecision
from app.domains.risk.service import RiskService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.registry import StrategyRegistry
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import Clock
from app.domains.trading.enums import OrderSide, OrderStatus, OrderType, ProductType, TimeInForce
from app.domains.trading.models import Order, Portfolio, Position
from app.domains.trading.service import TradingService

log = get_structured_logger(__name__)
audit_service = AuditTrailService()


class ExecutionPipelineRunner:
    """Executes a single end-to-end trading cycle across all domain subsystems with full distributed tracing."""

    def __init__(
        self,
        clock: Clock,
        session_manager: MarketSessionManager,
        portfolio_service: PortfolioConstructionService,
        risk_service: RiskService,
        event_bus: EventBus,
        metrics_tracker: ContinuousMetricsTracker,
        invariant_validator: InvariantValidator,
    ):
        self.clock = clock
        self.session_manager = session_manager
        self.portfolio_service = portfolio_service
        self.risk_service = risk_service
        self.event_bus = event_bus
        self.metrics_tracker = metrics_tracker
        self.invariant_validator = invariant_validator

    def run_cycle(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        mode: OrchestratorMode = OrchestratorMode.paper,
        provided_signals: list[TradingSignal] | None = None,
        strategy_ids: list[str] | None = None,
        enforce_market_hours: bool = False,
        config: PortfolioConstructionConfig | None = None,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
        volatilities: dict[uuid.UUID, Decimal] | None = None,
        sectors: dict[uuid.UUID, str] | None = None,
    ) -> ExecutionCycleResult:
        """Executes the full synchronized trading pipeline."""
        cycle_id = uuid.uuid4()
        now = self.clock.now()
        stage_latencies: dict[str, float] = {}
        t_start = time.perf_counter()

        with log_context(
            cycle_id=str(cycle_id),
            correlation_id=str(cycle_id),
            stage="pipeline_init",
        ), trace_span(
            "execution_cycle",
            kind=SpanKind.pipeline_stage,
            tags={"portfolio_id": str(portfolio_id), "mode": mode.value, "cycle_id": str(cycle_id)},
        ) as root_span:

            log.info("execution_cycle_started", portfolio_id=str(portfolio_id), mode=mode.value)
            audit_service.record(
                actor="orchestrator",
                component="pipeline",
                action="pipeline_started",
                entity_type="portfolio",
                entity_id=str(portfolio_id),
                metadata={"cycle_id": str(cycle_id), "mode": mode.value},
                db=db,
            )

            portfolio = db.get(Portfolio, portfolio_id)
            if not portfolio:
                log.error("portfolio_not_found", portfolio_id=str(portfolio_id))
                raise PipelineExecutionError("init", f"Portfolio {portfolio_id} not found")

            # -------------------------------------------------------------
            # STAGE 1: Session Validation
            # -------------------------------------------------------------
            with log_context(stage="session_validation"), trace_span("session_validation", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                if enforce_market_hours and mode != OrchestratorMode.backtest:
                    try:
                        self.session_manager.validate_can_trade(now, enforce=True)
                    except MarketClosedError as err:
                        duration_ms = (time.perf_counter() - t_start) * 1000.0
                        rec = ExecutionCycleRecord(
                            id=cycle_id,
                            portfolio_id=portfolio_id,
                            timestamp=now,
                            mode=mode.value,
                            duration_ms=duration_ms,
                            stage_latencies={"session_validation": (time.perf_counter() - t0) * 1000.0},
                            status=CycleStatus.skipped_market_closed.value,
                            error_message=str(err),
                        )
                        db.add(rec)
                        db.commit()
                        log.warning("cycle_skipped_market_closed", reason=str(err))
                        return ExecutionCycleResult(
                            cycle_id=cycle_id,
                            portfolio_id=portfolio_id,
                            timestamp=now,
                            mode=mode,
                            duration_ms=duration_ms,
                            status=CycleStatus.skipped_market_closed,
                            signals_evaluated_count=0,
                            candidate_orders_count=0,
                            risk_approved_count=0,
                            risk_rejected_count=0,
                            orders_submitted_count=0,
                            orders_filled_count=0,
                            stage_latencies=rec.stage_latencies,
                            error_message=str(err),
                        )
                stage_latencies["session_validation"] = round((time.perf_counter() - t0) * 1000.0, 4)

            # -------------------------------------------------------------
            # STAGE 2: Market Data Ingest & Snapshot
            # -------------------------------------------------------------
            with log_context(stage="market_data_ingest"), trace_span("market_data_ingest", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                md_breaker = global_circuit_breaker_registry.get_or_create("market_data")

                with md_breaker.protect():
                    active_instruments = list(db.scalars(select(Instrument)).all())
                    prices_map = dict(current_prices or {})
                    for inst in active_instruments:
                        if inst.id not in prices_map:
                            prices_map[inst.id] = Decimal("1000.00")  # Default fallback reference price

                self.event_bus.publish(
                    MarketDataUpdatedEvent(
                        instrument_count=len(prices_map),
                        latest_timestamp=now,
                    ),
                    db=db,
                )
                stage_latencies["market_data_ingest"] = round((time.perf_counter() - t0) * 1000.0, 4)

            # -------------------------------------------------------------
            # STAGE 3: Strategy Signal Evaluation
            # -------------------------------------------------------------
            with log_context(stage="strategy_evaluation"), trace_span("strategy_evaluation", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                signals: list[TradingSignal] = list(provided_signals or [])
                strat_ids = list(strategy_ids or ["manual_or_direct"])
                stage_latencies["strategy_evaluation"] = round((time.perf_counter() - t0) * 1000.0, 4)

                self.event_bus.publish(
                    StrategyEvaluationCompletedEvent(
                        signals_count=len(signals),
                        strategy_ids=strat_ids,
                        duration_ms=stage_latencies["strategy_evaluation"],
                    ),
                    db=db,
                )

            # -------------------------------------------------------------
            # STAGE 4: Portfolio Construction & Arbitration
            # -------------------------------------------------------------
            with log_context(stage="portfolio_construction"), trace_span("portfolio_construction", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                snapshot = self.portfolio_service.build_snapshot_from_db(
                    db=db,
                    portfolio_id=portfolio_id,
                    current_prices=prices_map,
                    volatilities=volatilities,
                    sectors=sectors,
                )

                plan = self.portfolio_service.construct_portfolio(
                    portfolio_snapshot=snapshot,
                    signals=signals,
                    config=config,
                    current_prices=prices_map,
                    instrument_sectors=sectors,
                    db=db,
                )
                stage_latencies["portfolio_construction"] = round((time.perf_counter() - t0) * 1000.0, 4)

                self.event_bus.publish(
                    PortfolioConstructionCompletedEvent(
                        plan_id=plan.plan_id,
                        candidate_orders_count=plan.total_candidates,
                        total_equity=plan.total_equity,
                        cash_allocated=plan.cash_allocated,
                    ),
                    db=db,
                )

            # -------------------------------------------------------------
            # STAGE 5, 6 & 7: Risk Gate, OMS Submission & Execution Simulation
            # -------------------------------------------------------------
            with log_context(stage="oms_and_execution"), trace_span("oms_and_execution", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                trading_service = TradingService(db=db, clock=self.clock, risk_service=self.risk_service)
                
                approved_count = 0
                rejected_count = 0
                orders_submitted = 0
                orders_filled = 0

                for cand in plan.candidate_orders:
                    side = OrderSide.buy if cand.side == "buy" else OrderSide.sell
                    est_p = prices_map.get(cand.instrument_id, cand.estimated_price)

                    with log_context(order_id=str(cand.candidate_id), symbol=cand.symbol):
                        try:
                            order = trading_service.submit_order(
                                portfolio_id=portfolio_id,
                                instrument_id=cand.instrument_id,
                                side=side,
                                order_type=OrderType.market,
                                quantity=cand.quantity,
                                limit_price=None,
                                stop_price=cand.stop_loss,
                                decision={
                                    "model_confidence": cand.confidence,
                                    "expected_return": cand.expected_return,
                                    "risk_reward_ratio": cand.risk_reward_ratio,
                                    "entry_reason": cand.reasoning,
                                    "summary": f"Orchestrated candidate order from plan {plan.plan_id}",
                                },
                            )

                            if order.status == OrderStatus.rejected:
                                rejected_count += 1
                                audit_service.record(
                                    actor="risk_engine",
                                    component="risk",
                                    action="risk_rejection",
                                    entity_type="candidate_order",
                                    entity_id=str(cand.candidate_id),
                                    metadata={"symbol": cand.symbol, "side": cand.side, "quantity": cand.quantity},
                                    db=db,
                                )
                            else:
                                approved_count += 1
                                orders_submitted += 1
                                audit_service.record(
                                    actor="oms",
                                    component="trading",
                                    action="order_submitted",
                                    entity_type="order",
                                    entity_id=str(order.id),
                                    metadata={"symbol": cand.symbol, "side": cand.side, "quantity": cand.quantity},
                                    db=db,
                                )
                                self.event_bus.publish(
                                    OrderSubmittedEvent(
                                        order_id=order.id,
                                        portfolio_id=portfolio_id,
                                        instrument_id=cand.instrument_id,
                                        symbol=cand.symbol,
                                        side=cand.side,
                                        quantity=cand.quantity,
                                        order_type="market",
                                    ),
                                    db=db,
                                )

                                # In paper trading mode, execute immediate fill simulation
                                if mode == OrchestratorMode.paper:
                                    fill = trading_service.execute_order(
                                        order_id=order.id,
                                        market_price=est_p,
                                        fill_quantity=cand.quantity,
                                    )
                                    if fill is not None:
                                        orders_filled += 1
                                        audit_service.record(
                                            actor="oms",
                                            component="trading",
                                            action="order_filled",
                                            entity_type="order",
                                            entity_id=str(order.id),
                                            metadata={"fill_id": str(fill.id), "price": str(fill.price), "quantity": fill.quantity},
                                            db=db,
                                        )
                                        self.event_bus.publish(
                                            OrderFilledEvent(
                                                order_id=order.id,
                                                fill_id=fill.id,
                                                fill_price=fill.price,
                                                fill_quantity=fill.quantity,
                                                commission=fill.total_charges,
                                            ),
                                            db=db,
                                        )

                        except Exception as err:
                            log.error("Failed to process candidate order %s: %s", cand.candidate_id, err)
                            rejected_count += 1

                stage_latencies["oms_and_execution"] = round((time.perf_counter() - t0) * 1000.0, 4)

                self.event_bus.publish(
                    RiskEvaluationCompletedEvent(
                        approved_count=approved_count,
                        rejected_count=rejected_count,
                    ),
                    db=db,
                )

            # -------------------------------------------------------------
            # STAGE 8: Invariant Verification & Continuous Metrics
            # -------------------------------------------------------------
            with log_context(stage="invariants_and_metrics"), trace_span("invariants_and_metrics", kind=SpanKind.pipeline_stage):
                t0 = time.perf_counter()
                db.flush()
                
                # Verify invariants
                self.invariant_validator.verify_all(
                    db=db,
                    portfolio_id=portfolio_id,
                    cycle_id=cycle_id,
                    raise_on_failure=False,
                )

                # Update metrics
                positions = list(db.scalars(select(Position).where(Position.portfolio_id == portfolio_id)).all())
                updated_portfolio = db.get(Portfolio, portfolio_id)
                if updated_portfolio:
                    metrics = self.metrics_tracker.calculate_metrics(
                        portfolio=updated_portfolio,
                        open_positions=positions,
                        current_time=now,
                        current_prices=prices_map,
                    )
                    self.event_bus.publish(
                        PortfolioUpdatedEvent(
                            portfolio_id=portfolio_id,
                            cash_balance=updated_portfolio.cash_balance,
                            total_equity=metrics.total_equity,
                            positions_count=len(positions),
                        ),
                        db=db,
                    )

                stage_latencies["invariants_and_metrics"] = round((time.perf_counter() - t0) * 1000.0, 4)

            # Record Execution Cycle
            total_duration_ms = (time.perf_counter() - t_start) * 1000.0
            cycle_rec = ExecutionCycleRecord(
                id=cycle_id,
                portfolio_id=portfolio_id,
                timestamp=now,
                mode=mode.value,
                duration_ms=total_duration_ms,
                signals_evaluated_count=len(signals),
                candidate_orders_count=plan.total_candidates,
                risk_approved_count=approved_count,
                risk_rejected_count=rejected_count,
                orders_submitted_count=orders_submitted,
                orders_filled_count=orders_filled,
                stage_latencies=stage_latencies,
                status=CycleStatus.success.value,
            )
            db.add(cycle_rec)
            db.commit()

            # Record performance telemetry
            global_performance_profiler.record_cycle(
                total_duration_ms=total_duration_ms,
                stage_latencies=stage_latencies,
                signals_count=len(signals),
                orders_submitted=orders_submitted,
                orders_filled=orders_filled,
            )

            audit_service.record(
                actor="orchestrator",
                component="pipeline",
                action="pipeline_completed",
                entity_type="portfolio",
                entity_id=str(portfolio_id),
                metadata={"cycle_id": str(cycle_id), "duration_ms": total_duration_ms, "orders_filled": orders_filled},
                db=db,
            )
            log.info("execution_cycle_completed", duration_ms=round(total_duration_ms, 3), orders_filled=orders_filled)

            return ExecutionCycleResult(
                cycle_id=cycle_id,
                portfolio_id=portfolio_id,
                timestamp=now,
                mode=mode,
                duration_ms=round(total_duration_ms, 3),
                status=CycleStatus.success,
                signals_evaluated_count=len(signals),
                candidate_orders_count=plan.total_candidates,
                risk_approved_count=approved_count,
                risk_rejected_count=rejected_count,
                orders_submitted_count=orders_submitted,
                orders_filled_count=orders_filled,
                stage_latencies=stage_latencies,
                error_message=None,
            )
