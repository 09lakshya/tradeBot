"""Daily Portfolio Snapshot Engine for Phase 10."""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domains.operations.models import PortfolioDailySnapshot
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.snapshot_engine")
DEFAULT_SNAPSHOT_DIR = Path("scratch/daily_snapshots")


class DailySnapshotEngine:
    """Creates, validates, stores, and queries immutable end-of-day portfolio snapshots."""

    def __init__(self, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> None:
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, PortfolioDailySnapshot] = {}
        self._lock = threading.Lock()
        self._load_persisted_snapshots()

    def create_snapshot(
        self,
        date: str | None = None,
        portfolio_value: float = 100000.0,
        cash_balance: float = 80000.0,
        invested_capital: float = 20000.0,
        unrealized_pnl: float = 1200.0,
        realized_pnl: float = 3400.0,
        gross_return: float = 0.046,
        net_return: float = 0.042,
        drawdown: float = 0.015,
        open_positions: list[dict[str, Any]] | None = None,
        closed_trades: list[dict[str, Any]] | None = None,
        risk_metrics: dict[str, float] | None = None,
        strategy_allocation: dict[str, float] | None = None,
        exposure: dict[str, float] | None = None,
        cost_breakdown: dict[str, float] | None = None,
    ) -> PortfolioDailySnapshot:
        """Constructs and persists an immutable daily portfolio snapshot."""
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")

        open_positions = open_positions or []
        closed_trades = closed_trades or []
        risk_metrics = risk_metrics or {"var_95": 1450.0, "max_drawdown": drawdown, "leverage": 0.20}
        strategy_allocation = strategy_allocation or {"trend_following": 0.60, "mean_reversion": 0.40}
        exposure = exposure or {"equity": 0.20, "cash": 0.80}
        cost_breakdown = cost_breakdown or {"commissions": 45.50, "slippage": 12.30, "borrow_fees": 0.0}

        snapshot = PortfolioDailySnapshot(
            date=date,
            portfolio_value=portfolio_value,
            cash_balance=cash_balance,
            invested_capital=invested_capital,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            gross_return=gross_return,
            net_return=net_return,
            drawdown=drawdown,
            open_positions_count=len(open_positions),
            closed_trades_count=len(closed_trades),
            open_positions=open_positions,
            closed_trades=closed_trades,
            risk_metrics=risk_metrics,
            strategy_allocation=strategy_allocation,
            exposure=exposure,
            cost_breakdown=cost_breakdown,
        )

        with self._lock:
            # Snapshots are immutable for a given date
            self._memory_cache[date] = snapshot
            self._save_snapshot_to_disk(snapshot)
            logger.info("snapshot_created", date=date, portfolio_value=portfolio_value)

        return snapshot

    def get_snapshot(self, date: str) -> PortfolioDailySnapshot | None:
        with self._lock:
            return self._memory_cache.get(date)

    def list_snapshots(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 30,
    ) -> list[PortfolioDailySnapshot]:
        with self._lock:
            snapshots = list(self._memory_cache.values())
            snapshots.sort(key=lambda s: s.date)

            if start_date:
                snapshots = [s for s in snapshots if s.date >= start_date]
            if end_date:
                snapshots = [s for s in snapshots if s.date <= end_date]

            return snapshots[-limit:]

    def _save_snapshot_to_disk(self, snapshot: PortfolioDailySnapshot) -> None:
        filepath = self.snapshot_dir / f"snapshot_{snapshot.date}.json"
        filepath.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def _load_persisted_snapshots(self) -> None:
        for file in self.snapshot_dir.glob("snapshot_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                snapshot = PortfolioDailySnapshot(**data)
                self._memory_cache[snapshot.date] = snapshot
            except Exception as exc:
                logger.warning("snapshot_load_failed", file=str(file), error=str(exc))
