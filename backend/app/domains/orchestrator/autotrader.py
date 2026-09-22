"""Autonomous paper-trading loop: runs cycles by itself while the market is open.

Nothing previously drove the pipeline. ``set_execution_callback`` was never
called, celery beat carried no trading task, and ``/scheduler/start`` only set an
interval without starting anything -- so the "autonomous scheduler" ticked
against an empty callback. This service is the missing driver.

Each cycle, while NSE regular hours are in session:

    watchlist -> live quotes -> strategy signals -> risk gate -> OMS -> fills

The market-hours gate is the session manager's, so weekends, holidays and the
pre-open/closing-auction windows are all handled in one place rather than by
clock arithmetic here. Outside the session the loop idles cheaply; it does not
need to be started at the opening bell.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.domains.orchestrator.deps import get_orchestrator_service
from app.domains.orchestrator.enums import OrchestratorMode
from app.domains.orchestrator.live_market import (
    LivePriceFeed,
    LiveSignalEngine,
    refresh_daily_bars,
    watchlist_instruments,
)
from app.domains.orchestrator.schemas import ExecutionCycleRequest
from app.domains.orchestrator.session_manager import IST_TZ, MarketSessionManager
from app.domains.portfolio.schemas import PortfolioConstructionConfig
from app.domains.trading.models import Portfolio

log = get_logger(__name__)


@dataclass
class CycleOutcome:
    """What one autonomous cycle did, for the status endpoint and the logs."""

    timestamp: datetime
    ran: bool
    reason: str = ""
    signals: int = 0
    candidates: int = 0
    approved: int = 0
    rejected: int = 0
    submitted: int = 0
    filled: int = 0
    duration_ms: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "ran": self.ran,
            "reason": self.reason,
            "signals": self.signals,
            "candidates": self.candidates,
            "approved": self.approved,
            "rejected": self.rejected,
            "submitted": self.submitted,
            "filled": self.filled,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


@dataclass
class AutoTraderState:
    running: bool = False
    started_at: datetime | None = None
    cycles_attempted: int = 0
    cycles_executed: int = 0
    last_outcome: CycleOutcome | None = None
    history: list[CycleOutcome] = field(default_factory=list)

    def record(self, outcome: CycleOutcome, keep: int = 50) -> None:
        self.cycles_attempted += 1
        if outcome.ran:
            self.cycles_executed += 1
        self.last_outcome = outcome
        self.history.append(outcome)
        del self.history[:-keep]


class AutoTrader:
    """Drives execution cycles on an interval, gated on the live market session."""

    def __init__(
        self,
        session_manager: MarketSessionManager | None = None,
        price_feed: LivePriceFeed | None = None,
        signal_engine: LiveSignalEngine | None = None,
    ) -> None:
        self.session_manager = session_manager or MarketSessionManager()
        self.price_feed = price_feed or LivePriceFeed()
        self.signal_engine = signal_engine or LiveSignalEngine()
        self.state = AutoTraderState()
        # When bars were last topped up, surfaced in status for observability.
        self._bars_refreshed_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # -- configuration ---------------------------------------------------
    @property
    def interval_seconds(self) -> float:
        return float(settings.autotrader_interval_seconds)

    @property
    def construction_config(self) -> PortfolioConstructionConfig:
        """Sizing and exposure limits for the cycle.

        Defaults are the engine's institutional ones (1% risk per trade, ATR x2
        stops, 10% per name, 25% per sector, max 10 positions); only the signal
        TTL is overridden, to match the cadence of the bars signals come from.
        """
        return PortfolioConstructionConfig(
            signal_ttl_seconds=int(settings.autotrader_signal_ttl_seconds),
        )

    @property
    def strategy_ids(self) -> list[str]:
        configured = [s.strip() for s in settings.autotrader_strategies.split(",") if s.strip()]
        if configured:
            return configured
        from app.domains.strategies.registry import StrategyRegistry

        return [m.strategy_id for m in StrategyRegistry.list_strategies()]

    # -- one cycle -------------------------------------------------------
    def run_cycle(self, force: bool = False) -> CycleOutcome:
        """Execute a single cycle. ``force`` bypasses the market-hours gate."""
        now = datetime.now(UTC)
        started = now

        if not force and not self.session_manager.is_market_open(now):
            state = self.session_manager.get_session_state(now)
            return CycleOutcome(timestamp=now, ran=False, reason=f"market {state.value}")

        with SessionLocal() as db:
            portfolio = None
            configured = str(settings.autotrader_portfolio_id).strip()
            if configured:
                # A malformed id must not take the loop down every cycle: fall
                # back to the default wallet and say so. (dotenv leaves an inline
                # comment in the value when the value is empty, which is exactly
                # how this arrives as junk.)
                try:
                    portfolio = db.get(Portfolio, uuid.UUID(configured))
                except (ValueError, AttributeError):
                    log.warning("autotrader_portfolio_id_invalid", value=configured[:60])
            if portfolio is None:
                portfolio = db.scalars(select(Portfolio).order_by(Portfolio.created_at)).first()
            if portfolio is None:
                return CycleOutcome(
                    timestamp=now, ran=False, reason="no funded wallet: add money first"
                )
            portfolio_id: uuid.UUID = portfolio.id

            instruments = watchlist_instruments(db)
            if not instruments:
                return CycleOutcome(
                    timestamp=now, ran=False,
                    reason="watchlist empty: run bootstrap_live_universe.py",
                )
            limit = int(settings.autotrader_symbol_limit)
            if limit > 0:
                instruments = instruments[:limit]

            try:
                # Top up bars every cycle (~7s for 200 symbols, against a 15
                # minute interval). Once a day is not enough: today's bar is
                # still forming, so a single pre-open refresh would leave every
                # strategy reading yesterday's close for the whole session.
                refresh_daily_bars(db, instruments)
                db.commit()
                self._bars_refreshed_at = datetime.now(IST_TZ)

                prices = self.price_feed.fetch(instruments)
                # Never trade an instrument we could not price: the pipeline would
                # otherwise fall back to a placeholder and size against fiction.
                priced = [i for i in instruments if i.id in prices]

                signals = self.signal_engine.generate(
                    db=db, portfolio_id=portfolio_id, instruments=priced,
                    strategy_ids=self.strategy_ids, prices=prices,
                )

                service = get_orchestrator_service()
                result = service.execute_cycle(
                    db=db,
                    req=ExecutionCycleRequest(
                        portfolio_id=portfolio_id,
                        mode=OrchestratorMode.paper,
                        strategy_ids=self.strategy_ids,
                        enforce_market_hours=not force,
                        config=self.construction_config,
                    ),
                    provided_signals=signals,
                    current_prices=prices,
                )
                db.commit()
            except Exception as exc:  # noqa: BLE001 - a bad cycle must not kill the loop
                db.rollback()
                log.error("autotrader_cycle_failed", error=str(exc), exc_info=True)
                return CycleOutcome(
                    timestamp=now, ran=False, reason="error", error=str(exc)[:500],
                    duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                )

        outcome = CycleOutcome(
            timestamp=now,
            ran=True,
            reason=result.status.value,
            signals=result.signals_evaluated_count,
            candidates=result.candidate_orders_count,
            approved=result.risk_approved_count,
            rejected=result.risk_rejected_count,
            submitted=result.orders_submitted_count,
            filled=result.orders_filled_count,
            duration_ms=result.duration_ms,
        )
        log.info("autotrader_cycle", **outcome.as_dict())
        return outcome

    # -- the loop --------------------------------------------------------
    async def _loop(self) -> None:
        log.info(
            "autotrader_started",
            interval_seconds=self.interval_seconds,
            strategies=len(self.strategy_ids),
        )
        while not self._stop.is_set():
            try:
                # The cycle does blocking network and DB work; keep it off the
                # event loop so the API stays responsive while it runs.
                outcome = await asyncio.to_thread(self.run_cycle)
                self.state.record(outcome)
            except Exception as exc:  # noqa: BLE001
                log.error("autotrader_loop_error", error=str(exc), exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue
        log.info("autotrader_stopped")

    def start(self) -> bool:
        if self._task and not self._task.done():
            return False
        self._stop = asyncio.Event()
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.state.running = True
        self.state.started_at = datetime.now(UTC)
        return True

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.state.running = False

    def status(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        session = self.session_manager.get_session_state(now)
        return {
            "running": self.state.running,
            "enabled_by_config": bool(settings.autotrader_enabled),
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "interval_seconds": self.interval_seconds,
            "strategies": len(self.strategy_ids),
            "symbol_limit": int(settings.autotrader_symbol_limit),
            "market_session": session.value,
            "market_open": self.session_manager.is_market_open(now),
            "bars_refreshed_at": self._bars_refreshed_at.isoformat()
            if self._bars_refreshed_at
            else None,
            "cycles_attempted": self.state.cycles_attempted,
            "cycles_executed": self.state.cycles_executed,
            "last_cycle": self.state.last_outcome.as_dict() if self.state.last_outcome else None,
            "recent": [o.as_dict() for o in self.state.history[-10:]],
        }


_autotrader = AutoTrader()


def get_autotrader() -> AutoTrader:
    return _autotrader
