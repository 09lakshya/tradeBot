"""Portfolio Construction Service orchestrating the complete pipeline and audit persistence."""
import logging
import time
import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.market_data.models import Instrument
from app.domains.portfolio.aggregator import SignalAggregator
from app.domains.portfolio.arbitration import SignalArbitrationEngine
from app.domains.portfolio.models import (
    ArbitrationAuditRecord,
    CandidateOrderRecord,
    PortfolioConstructionPlan,
)
from app.domains.portfolio.optimizer import PortfolioOptimizer
from app.domains.portfolio.ranking import SignalRankingEngine
from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    CandidateOrder,
    PortfolioConstructionConfig,
    PortfolioConstructionPlanResponse,
    PortfolioEngineMetricsResponse,
    PortfolioSnapshot,
    PositionSnapshot,
)
from app.domains.portfolio.sizing import PositionSizingEngine
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import Clock, SystemClock
from app.domains.trading.models import Portfolio, Position

log = logging.getLogger(__name__)


class PortfolioConstructionService:
    """Core domain service for signal aggregation, ranking, arbitration, optimization, and candidate order generation."""

    def __init__(
        self,
        clock: Clock | None = None,
        aggregator: SignalAggregator | None = None,
        ranking_engine: SignalRankingEngine | None = None,
        arbitration_engine: SignalArbitrationEngine | None = None,
        optimizer: PortfolioOptimizer | None = None,
        sizing_engine: PositionSizingEngine | None = None,
    ):
        self.clock = clock or SystemClock()
        self.aggregator = aggregator or SignalAggregator()
        self.ranking_engine = ranking_engine or SignalRankingEngine()
        self.arbitration_engine = arbitration_engine or SignalArbitrationEngine()
        self.optimizer = optimizer or PortfolioOptimizer()
        self.sizing_engine = sizing_engine or PositionSizingEngine()

        # Telemetry metrics
        self._total_plans: int = 0
        self._total_candidate_orders: int = 0
        self._total_conflicts_resolved: int = 0
        self._total_optimization_latency_ms: float = 0.0
        self._total_ranking_latency_ms: float = 0.0
        self._last_eval_time: datetime | None = None

    def construct_portfolio(
        self,
        portfolio_snapshot: PortfolioSnapshot,
        signals: Sequence[TradingSignal],
        config: PortfolioConstructionConfig | None = None,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
        instrument_sectors: dict[uuid.UUID, str] | None = None,
        strategy_sharpes: dict[str, float] | None = None,
        db: Session | None = None,
    ) -> PortfolioConstructionPlanResponse:
        """Executes the pure mathematical portfolio construction pipeline."""
        t_start = time.perf_counter()
        plan_id = uuid.uuid4()
        cfg = config or PortfolioConstructionConfig()
        current_time = self.clock.now()

        # 1. Signal Aggregation & TTL Validation
        # The aggregator carries its own default TTL, so a config that sets
        # `signal_ttl_seconds` was silently ignored: the knob existed, was
        # documented, and did nothing. Daily-bar signals are hours old by
        # construction and were all discarded as stale at the 1h default.
        aggregator = self.aggregator
        if cfg.signal_ttl_seconds != aggregator.default_ttl_seconds:
            aggregator = SignalAggregator(default_ttl_seconds=cfg.signal_ttl_seconds)
        grouped_signals = aggregator.aggregate(
            signals=signals,
            current_time=current_time,
            portfolio_snapshot=portfolio_snapshot,
            min_daily_volume=cfg.min_daily_volume,
        )

        all_active_signals = [sig for group in grouped_signals.values() for sig in group]

        # 2. Multi-factor Ranking
        t_rank_0 = time.perf_counter()
        ranking_engine = (
            SignalRankingEngine(
                method=cfg.ranking_method,
                weights=cfg.ranking_weights,
            )
            if config
            else self.ranking_engine
        )
        ranked_scores = ranking_engine.rank_signals(
            signals=all_active_signals,
            current_time=current_time,
            portfolio_snapshot=portfolio_snapshot,
            strategy_sharpe_ratios=strategy_sharpes,
        )
        t_rank_1 = time.perf_counter()
        ranking_latency_ms = (t_rank_1 - t_rank_0) * 1000.0
        ranking_scores_map = {sc.signal_id: sc for sc in ranked_scores}

        # 3. Signal Arbitration per instrument
        arbitration_engine = (
            SignalArbitrationEngine(
                method=cfg.arbitration_method,
                neutral_threshold=cfg.arbitration_neutral_threshold,
            )
            if config
            else self.arbitration_engine
        )

        decisions_map: dict[uuid.UUID, ArbitrationDecision] = {}
        for inst_id, inst_sigs in grouped_signals.items():
            dec = arbitration_engine.arbitrate(
                instrument_id=inst_id,
                signals=inst_sigs,
                ranking_scores=ranking_scores_map,
            )
            decisions_map[inst_id] = dec

        # 4. Constrained Portfolio Optimization
        t_opt_0 = time.perf_counter()
        target_weights, opt_explanations = self.optimizer.optimize(
            decisions=list(decisions_map.values()),
            snapshot=portfolio_snapshot,
            ranking_scores=ranking_scores_map,
            config=cfg,
            instrument_sectors=instrument_sectors,
        )

        # 5. Position Sizing & Explainable Candidate Orders
        candidate_orders = self.sizing_engine.size_positions(
            plan_id=plan_id,
            decisions=decisions_map,
            target_weights=target_weights,
            snapshot=portfolio_snapshot,
            signals_map=grouped_signals,
            ranking_scores=ranking_scores_map,
            config=cfg,
            current_prices=current_prices,
            optimization_explanations=opt_explanations,
        )
        t_opt_1 = time.perf_counter()
        opt_latency_ms = (t_opt_1 - t_opt_0) * 1000.0

        # Calculations for plan summary
        allocated_notional = sum(c.estimated_notional for c in candidate_orders)
        reserve_cash_amount = portfolio_snapshot.total_equity * cfg.reserve_cash_pct

        summary_metrics = {
            "raw_signal_count": len(signals),
            "active_signal_count": len(all_active_signals),
            "instruments_evaluated": len(grouped_signals),
            "candidates_produced": len(candidate_orders),
            "total_allocated_notional": float(allocated_notional),
            "reserve_cash_amount": float(reserve_cash_amount),
            "ranking_latency_ms": ranking_latency_ms,
            "optimization_latency_ms": opt_latency_ms,
            "total_latency_ms": (time.perf_counter() - t_start) * 1000.0,
        }

        # 6. Database Persistence (Audit Trail)
        if db:
            self._persist_plan(
                db=db,
                plan_id=plan_id,
                portfolio_id=portfolio_snapshot.portfolio_id,
                timestamp=current_time,
                cfg=cfg,
                portfolio_snapshot=portfolio_snapshot,
                allocated_notional=allocated_notional,
                reserve_cash_amount=reserve_cash_amount,
                candidate_orders=candidate_orders,
                decisions=list(decisions_map.values()),
                summary_metrics=summary_metrics,
            )

        # Update telemetry
        self._total_plans += 1
        self._total_candidate_orders += len(candidate_orders)
        self._total_conflicts_resolved += sum(
            1 for d in decisions_map.values() if d.conflict_type.startswith("BUY_VS_SELL")
        )
        self._total_ranking_latency_ms += ranking_latency_ms
        self._total_optimization_latency_ms += opt_latency_ms
        self._last_eval_time = current_time

        return PortfolioConstructionPlanResponse(
            plan_id=plan_id,
            portfolio_id=portfolio_snapshot.portfolio_id,
            timestamp=current_time,
            allocation_policy=cfg.allocation_policy,
            sizing_method=cfg.sizing_method,
            total_equity=portfolio_snapshot.total_equity,
            cash_allocated=allocated_notional,
            reserve_cash=reserve_cash_amount,
            total_candidates=len(candidate_orders),
            candidate_orders=candidate_orders,
            arbitration_decisions=list(decisions_map.values()),
            summary_metrics=summary_metrics,
            created_at=current_time,
        )

    def build_snapshot_from_db(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
        volatilities: dict[uuid.UUID, Decimal] | None = None,
        sectors: dict[uuid.UUID, str] | None = None,
    ) -> PortfolioSnapshot:
        """Helper to construct an immutable PortfolioSnapshot from existing database state."""
        portfolio = db.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found in database")

        prices = current_prices or {}
        vols = volatilities or {}
        sec_map = sectors or {}

        # Fetch open positions
        positions_stmt = select(Position).where(
            Position.portfolio_id == portfolio_id, Position.quantity != 0
        )
        db_positions = list(db.scalars(positions_stmt).all())

        positions_map: dict[uuid.UUID, PositionSnapshot] = {}
        total_positions_val = Decimal("0.00")
        sector_exp: dict[str, Decimal] = {}
        strategy_exp: dict[str, Decimal] = {}

        for p in db_positions:
            mkt_price = prices.get(p.instrument_id, p.avg_entry_price)
            notional = abs(p.quantity) * mkt_price
            total_positions_val += notional
            sec = sec_map.get(p.instrument_id, "General")
            sector_exp[sec] = sector_exp.get(sec, Decimal("0.00")) + notional

            inst = db.get(Instrument, p.instrument_id)
            sym = inst.trading_symbol if inst else str(p.instrument_id)

            unrealized = (mkt_price - p.avg_entry_price) * p.quantity

            positions_map[p.instrument_id] = PositionSnapshot(
                instrument_id=p.instrument_id,
                symbol=sym,
                quantity=p.quantity,
                average_entry_price=p.avg_entry_price,
                current_market_price=mkt_price,
                current_notional=notional,
                current_weight=Decimal("0.0000"),  # calculated below
                unrealized_pnl=unrealized,
                realized_pnl=p.realized_pnl,
                sector=sec,
            )

        total_equity = portfolio.cash_balance + total_positions_val
        current_weights: dict[uuid.UUID, Decimal] = {}
        if total_equity > 0:
            for inst_id, pos in positions_map.items():
                w = (pos.current_notional / total_equity).quantize(Decimal("0.0001"))
                current_weights[inst_id] = w

        return PortfolioSnapshot(
            portfolio_id=portfolio_id,
            timestamp=self.clock.now(),
            cash_balance=portfolio.cash_balance,
            reserved_cash=portfolio.reserved_cash,
            total_equity=total_equity,
            positions=positions_map,
            sector_exposures=sector_exp,
            strategy_exposures=strategy_exp,
            current_weights=current_weights,
            unrealized_pnl=sum((p.unrealized_pnl for p in positions_map.values()), Decimal("0.00")),
            realized_pnl=sum((p.realized_pnl for p in positions_map.values()), Decimal("0.00")),
            volatilities=vols,
        )

    def get_metrics(self) -> PortfolioEngineMetricsResponse:
        """Returns aggregate performance telemetry."""
        avg_opt_lat = (
            self._total_optimization_latency_ms / self._total_plans
            if self._total_plans > 0
            else 0.0
        )
        avg_rank_lat = (
            self._total_ranking_latency_ms / self._total_plans
            if self._total_plans > 0
            else 0.0
        )
        avg_candidates = (
            self._total_candidate_orders / self._total_plans
            if self._total_plans > 0
            else 0.0
        )

        return PortfolioEngineMetricsResponse(
            total_plans_executed=self._total_plans,
            total_candidate_orders_generated=self._total_candidate_orders,
            avg_optimization_latency_ms=avg_opt_lat,
            avg_ranking_latency_ms=avg_rank_lat,
            avg_candidate_count_per_plan=avg_candidates,
            arbitration_conflict_count=self._total_conflicts_resolved,
            last_evaluation_timestamp=self._last_eval_time,
        )

    def _persist_plan(
        self,
        db: Session,
        plan_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        timestamp: datetime,
        cfg: PortfolioConstructionConfig,
        portfolio_snapshot: PortfolioSnapshot,
        allocated_notional: Decimal,
        reserve_cash_amount: Decimal,
        candidate_orders: list[CandidateOrder],
        decisions: list[ArbitrationDecision],
        summary_metrics: dict[str, Any],
    ) -> None:
        """Writes execution records and immutable candidate orders to the database."""
        plan = PortfolioConstructionPlan(
            id=plan_id,
            portfolio_id=portfolio_id,
            timestamp=timestamp,
            allocation_policy=cfg.allocation_policy.value,
            sizing_method=cfg.sizing_method.value,
            total_equity=portfolio_snapshot.total_equity,
            cash_allocated=allocated_notional,
            reserve_cash=reserve_cash_amount,
            config_snapshot=cfg.model_dump(mode="json"),
            summary_metrics=summary_metrics,
        )
        db.add(plan)

        for c in candidate_orders:
            rec = CandidateOrderRecord(
                id=c.candidate_id,
                plan_id=plan_id,
                portfolio_id=portfolio_id,
                instrument_id=c.instrument_id,
                symbol=c.symbol,
                side=c.side.value,
                product_type=c.product_type.value,
                quantity=c.quantity,
                target_weight=c.target_weight,
                current_weight=c.current_weight,
                estimated_price=c.estimated_price,
                estimated_notional=c.estimated_notional,
                stop_loss=c.stop_loss,
                take_profit=c.take_profit,
                confidence=Decimal(str(round(c.confidence, 4))),
                expected_return=c.expected_return,
                expected_risk=c.expected_risk,
                risk_reward_ratio=c.risk_reward_ratio,
                strategy_sources=c.strategy_sources,
                signal_sources=[str(sid) for sid in c.signal_sources],
                scoring_breakdown=c.ranking_breakdown,
                sizing_breakdown=c.sizing_breakdown,
                transaction_costs_json=c.transaction_costs.model_dump(mode="json"),
                reasoning=c.reasoning,
                explainability_trace=c.explainability_trace,
                status=c.status.value,
            )
            db.add(rec)

        for d in decisions:
            arb_rec = ArbitrationAuditRecord(
                id=uuid.uuid4(),
                plan_id=plan_id,
                instrument_id=d.instrument_id,
                symbol=d.symbol,
                conflict_type=d.conflict_type,
                resolution_method=d.resolution_method.value,
                input_signals=[str(sid) for sid in d.selected_signals + d.discarded_signals],
                winning_signal={"winning_side": d.winning_side.value if d.winning_side else None},
                explainability=d.reason,
            )
            db.add(arb_rec)

        db.flush()
