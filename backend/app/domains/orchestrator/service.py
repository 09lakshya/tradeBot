"""Core Execution Orchestrator Service providing end-to-end management of the trading pipeline."""
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Sequence
import uuid
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domains.orchestrator.enums import CycleStatus, OrchestratorMode
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.health import HealthMonitor
from app.domains.orchestrator.invariants import InvariantValidator
from app.domains.orchestrator.metrics import ContinuousMetricsTracker
from app.domains.orchestrator.models import ExecutionCycleRecord, OrchestratorEventRecord
from app.domains.orchestrator.pipeline import ExecutionPipelineRunner
from app.domains.orchestrator.schemas import (
    ContinuousMetricsResponse,
    ExecutionCycleRequest,
    ExecutionCycleResult,
    HealthMetricsResponse,
    InvariantReportResponse,
    PipelineStatusResponse,
    SessionStatusResponse,
)
from app.domains.orchestrator.scheduler import ExecutionScheduler
from app.domains.orchestrator.session_manager import MarketSessionManager
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.risk.service import RiskService
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import Clock, SystemClock
from app.domains.trading.models import Portfolio, Position

log = logging.getLogger(__name__)


class ExecutionOrchestratorService:
    """Production coordinator service managing market scanning, strategies, optimization, risk, and execution."""

    def __init__(
        self,
        clock: Clock | None = None,
        session_manager: MarketSessionManager | None = None,
        event_bus: EventBus | None = None,
        scheduler: ExecutionScheduler | None = None,
        health_monitor: HealthMonitor | None = None,
        metrics_tracker: ContinuousMetricsTracker | None = None,
        invariant_validator: InvariantValidator | None = None,
        portfolio_service: PortfolioConstructionService | None = None,
        risk_service: RiskService | None = None,
    ):
        self.clock = clock or SystemClock()
        self.session_manager = session_manager or MarketSessionManager()
        self.event_bus = event_bus or EventBus()
        self.scheduler = scheduler or ExecutionScheduler(clock=self.clock)
        self.health_monitor = health_monitor or HealthMonitor(clock=self.clock)
        self.metrics_tracker = metrics_tracker or ContinuousMetricsTracker()
        self.invariant_validator = invariant_validator or InvariantValidator()
        self.risk_service = risk_service or RiskService(clock=self.clock)
        self.portfolio_service = portfolio_service or PortfolioConstructionService(
            clock=self.clock,
        )
        self.pipeline = ExecutionPipelineRunner(
            clock=self.clock,
            session_manager=self.session_manager,
            portfolio_service=self.portfolio_service,
            risk_service=self.risk_service,
            event_bus=self.event_bus,
            metrics_tracker=self.metrics_tracker,
            invariant_validator=self.invariant_validator,
        )

        self._current_mode = OrchestratorMode.paper
        self._total_cycles_executed = 0
        self._total_cycle_time_ms = 0.0
        self._last_cycle_timestamp: datetime | None = None
        self._last_cycle_status: CycleStatus | None = None

    def execute_cycle(
        self,
        db: Session,
        req: ExecutionCycleRequest,
        provided_signals: list[TradingSignal] | None = None,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
        volatilities: dict[uuid.UUID, Decimal] | None = None,
        sectors: dict[uuid.UUID, str] | None = None,
    ) -> ExecutionCycleResult:
        """Executes a single end-to-end trading cycle."""
        res = self.pipeline.run_cycle(
            db=db,
            portfolio_id=req.portfolio_id,
            mode=req.mode,
            provided_signals=provided_signals,
            strategy_ids=req.strategy_ids,
            enforce_market_hours=req.enforce_market_hours,
            config=req.config,
            current_prices=current_prices,
            volatilities=volatilities,
            sectors=sectors,
        )

        self._total_cycles_executed += 1
        self._total_cycle_time_ms += res.duration_ms
        self._last_cycle_timestamp = res.timestamp
        self._last_cycle_status = res.status
        self._current_mode = req.mode

        # Update health probe metrics
        for stage, lat in res.stage_latencies.items():
            self.health_monitor.record_stage_latency(stage, lat)

        return res

    def get_pipeline_status(self) -> PipelineStatusResponse:
        """Returns overall operational status and cycle statistics."""
        avg_duration = (
            (self._total_cycle_time_ms / self._total_cycles_executed)
            if self._total_cycles_executed > 0
            else 0.0
        )
        return PipelineStatusResponse(
            is_running=True,
            scheduler_active=self.scheduler.is_running,
            current_mode=self._current_mode,
            last_cycle_timestamp=self._last_cycle_timestamp,
            last_cycle_status=self._last_cycle_status,
            total_cycles_executed=self._total_cycles_executed,
            average_cycle_duration_ms=round(avg_duration, 3),
        )

    def get_session_status(self) -> SessionStatusResponse:
        """Returns current Indian market session details."""
        return self.session_manager.get_session_status(self.clock.now())

    def get_health_metrics(self, db: Session | None = None) -> HealthMetricsResponse:
        """Returns latency and health diagnostic report."""
        return self.health_monitor.get_health_report(db=db)

    def get_continuous_metrics(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
    ) -> ContinuousMetricsResponse:
        """Returns latest continuous financial performance metrics."""
        portfolio = db.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        positions = list(db.scalars(select(Position).where(Position.portfolio_id == portfolio_id)).all())
        return self.metrics_tracker.calculate_metrics(
            portfolio=portfolio,
            open_positions=positions,
            current_time=self.clock.now(),
            current_prices=current_prices,
        )

    def verify_invariants(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> InvariantReportResponse:
        """Executes on-demand invariant checks."""
        return self.invariant_validator.verify_all(
            db=db,
            portfolio_id=portfolio_id,
            raise_on_failure=False,
        )

    def get_cycle_history(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        limit: int = 50,
    ) -> list[ExecutionCycleRecord]:
        """Retrieves paginated history of execution cycles."""
        stmt = (
            select(ExecutionCycleRecord)
            .where(ExecutionCycleRecord.portfolio_id == portfolio_id)
            .order_by(desc(ExecutionCycleRecord.timestamp))
            .limit(limit)
        )
        return list(db.scalars(stmt).all())
