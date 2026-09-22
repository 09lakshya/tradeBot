"""Backtest Service Orchestrator."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import PointInTimeDataFeed
from app.domains.backtest.driver import BacktestEngine
from app.domains.backtest.enums import BacktestSegmentType, BacktestStatus
from app.domains.backtest.exceptions import BacktestExecutionError
from app.domains.backtest.models import Backtest, BacktestResult, BacktestTrade
from app.domains.backtest.monte_carlo import MonteCarloResult, MonteCarloSimulator
from app.domains.backtest.schemas import BacktestCreateRequest, MonteCarloConfig, SlippageConfig
from app.domains.backtest.slippage import create_slippage_model
from app.domains.backtest.strategy_adapter import (
    DomainStrategyBacktestAdapter,
    BaseBacktestStrategy,
    BuyAndHoldStrategy,
    SMACrossoverStrategy,
)
from app.domains.metrics.calculator import PerformanceMetricsCalculator
from app.domains.risk.service import RiskService
from app.domains.trading.clock import ReplayClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.service import TradingService


def _get_strategy_instance(strategy_id: str, params: dict) -> BaseBacktestStrategy:
    """Resolve a strategy id to a runnable backtest strategy.

    Only ``sma_crossover`` was mapped here; every other id fell through to
    BuyAndHold, so backtesting any of the other registered strategies silently
    measured buy-and-hold and reported it under that strategy's name. The
    strategy domain's own registry is the source of truth, and
    DomainStrategyBacktestAdapter already exists to run those instances here.
    """
    if strategy_id == "SMACrossoverStrategy":
        return SMACrossoverStrategy(params)
    if strategy_id.lower() == "buy_and_hold":
        return BuyAndHoldStrategy(params)

    from app.domains.strategies.registry import StrategyRegistry

    try:
        domain_strategy = StrategyRegistry.create_instance(strategy_id, params=params or None)
    except Exception as exc:  # noqa: BLE001 - unknown id must be loud, not silently benchmarked
        raise ValueError(
            f"Unknown strategy_id {strategy_id!r}: not in the strategy registry"
        ) from exc
    return DomainStrategyBacktestAdapter(domain_strategy)


class BacktestService:
    """High-level service managing backtests, walk-forward runs, and Monte Carlo analyses."""

    def __init__(self, db: Session):
        self.db = db

    def create_backtest(self, req: BacktestCreateRequest) -> Backtest:
        """Create and persist a new backtest configuration."""
        config_snap = {
            "strategy_id": req.strategy_id,
            "strategy_version": req.strategy_version,
            "strategy_params": req.strategy_params,
            "cost_profile_name": req.cost_profile_name,
            "slippage": req.slippage.model_dump(mode="json"),
            "benchmark": req.benchmark.value,
            "validation_method": req.validation_method.value,
            "walk_forward_config": req.walk_forward_config.model_dump(mode="json") if req.walk_forward_config else None,
            "random_seed": req.random_seed,
        }

        bt = Backtest(
            name=req.name,
            strategy_id=req.strategy_id,
            strategy_version=req.strategy_version,
            random_seed=req.random_seed,
            instrument_ids=[str(i) for i in req.instrument_ids],
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            config_snapshot=config_snap,
            status=BacktestStatus.queued,
        )
        self.db.add(bt)
        self.db.commit()
        self.db.refresh(bt)
        return bt

    def run_backtest(
        self,
        backtest_id: uuid.UUID,
        data_feed: PointInTimeDataFeed | None = None,
    ) -> Backtest:
        """Execute the backtest through the shared OMS and Risk Engine."""
        bt = self.db.get(Backtest, backtest_id)
        if not bt:
            raise ValueError(f"Backtest {backtest_id} not found.")

        bt.status = BacktestStatus.running
        self.db.commit()

        try:
            # 1. Setup isolated Replay Clock, Cost Engine, and Risk Service
            start_dt = datetime.combine(bt.start_date, datetime.min.time(), tzinfo=UTC)
            clock = ReplayClock(start_time=start_dt)
            cost_profile = bt.config_snapshot.get("cost_profile_name", "zerodha")
            cost_engine = CostEngine(default_profile=cost_profile if cost_profile in CostEngine._PROFILES else "zerodha")
            risk_service = RiskService(clock=clock)
            
            # 2. Setup isolated Portfolio and TradingService
            trading = TradingService(db=self.db, clock=clock, cost_engine=cost_engine, risk_service=risk_service)
            port = trading.create_portfolio(name=f"BT_{bt.name[:20]}_{bt.id}", initial_capital=bt.initial_capital)
            bt.portfolio_id = port.id
            self.db.commit()

            # 3. Setup Slippage and Strategy
            slip_cfg_dict = bt.config_snapshot.get("slippage", {})
            slip_cfg = SlippageConfig(**slip_cfg_dict) if slip_cfg_dict else SlippageConfig()
            slippage_model = create_slippage_model(slip_cfg, random_seed=bt.random_seed)

            strategy = _get_strategy_instance(
                bt.strategy_id,
                bt.config_snapshot.get("strategy_params", {}),
            )

            # 4. Prepare Point-in-Time Data Feed if not injected
            if data_feed is None:
                inst_uuids = [uuid.UUID(i) for i in bt.instrument_ids]
                data_feed = PointInTimeDataFeed.from_database(
                    db=self.db,
                    clock=clock,
                    instrument_ids=inst_uuids,
                    start_date=bt.start_date,
                    end_date=bt.end_date,
                )

            # 5. Execute Simulation Loop
            engine = BacktestEngine(
                db=self.db,
                clock=clock,
                trading_service=trading,
                risk_service=risk_service,
                data_feed=data_feed,
                strategy=strategy,
                slippage_model=slippage_model,
                random_seed=bt.random_seed,
            )

            exec_result = engine.run(portfolio_id=port.id)

            # 6. Calculate Metrics
            equity_series = [float(p.equity) for p in exec_result.equity_curve]
            trade_pnls = [float(t.realized_pnl) for t in exec_result.trades]
            perf_report = PerformanceMetricsCalculator.calculate(
                equity_series=equity_series,
                trade_pnls=trade_pnls,
            )

            # 7. Persist Results and Trade Audit Trail
            eq_curve_json = [
                {
                    "ts": p.timestamp.isoformat(),
                    "equity": float(p.equity),
                    "cash": float(p.cash),
                    "drawdown_pct": float(p.drawdown_pct),
                }
                for p in exec_result.equity_curve
            ]

            result_row = BacktestResult(
                backtest_id=bt.id,
                segment_type=BacktestSegmentType.full,
                segment_index=0,
                segment_start=bt.start_date,
                segment_end=bt.end_date,
                metrics=perf_report.to_dict(),
                equity_curve=eq_curve_json,
                underwater_curve=[{"ts": p["ts"], "drawdown_pct": p["drawdown_pct"]} for p in eq_curve_json],
                trade_count=len(exec_result.trades),
            )
            self.db.add(result_row)

            for t in exec_result.trades:
                trade_row = BacktestTrade(
                    backtest_id=bt.id,
                    order_id=t.order_id,
                    fill_id=t.fill_id,
                    signal_id=t.signal_id,
                    strategy_id=t.strategy_id,
                    instrument_id=t.instrument_id,
                    symbol=t.symbol,
                    side=t.side.value,
                    quantity=t.quantity,
                    execution_price=t.execution_price,
                    slippage=t.slippage,
                    total_fees=t.total_fees,
                    fee_breakdown=t.fee_breakdown,
                    realized_pnl=t.realized_pnl,
                    return_pct=Decimal("0.0000"),
                    risk_verdict_token=t.risk_verdict_token,
                    executed_at=t.executed_at,
                )
                self.db.add(trade_row)

            bt.status = BacktestStatus.completed
            self.db.commit()
            self.db.refresh(bt)
            return bt

        except Exception as e:
            self.db.rollback()
            bt = self.db.get(Backtest, backtest_id)
            if bt:
                bt.status = BacktestStatus.failed
                bt.error = str(e)[:2000]
                self.db.commit()
            raise BacktestExecutionError(backtest_id, str(e), original_exception=e)

    def run_monte_carlo(self, backtest_id: uuid.UUID, config: MonteCarloConfig) -> MonteCarloResult:
        """Run Monte Carlo simulation on completed backtest trades."""
        bt = self.db.get(Backtest, backtest_id)
        if not bt or bt.status != BacktestStatus.completed:
            raise ValueError(f"Backtest {backtest_id} not completed.")

        trades_stmt = select(BacktestTrade).where(BacktestTrade.backtest_id == backtest_id)
        trades = list(self.db.scalars(trades_stmt))
        trade_pnls = [float(t.realized_pnl) for t in trades]

        return MonteCarloSimulator.simulate(
            trade_pnls=trade_pnls,
            initial_capital=float(bt.initial_capital),
            config=config,
        )

    def get_backtest(self, backtest_id: uuid.UUID) -> Backtest | None:
        """Retrieve backtest by ID."""
        return self.db.get(Backtest, backtest_id)
