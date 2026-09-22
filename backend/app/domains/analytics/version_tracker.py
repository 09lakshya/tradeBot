"""Strategy Version Tracking — Strategy version performance comparison over time."""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.analytics.models import TradeJournalEntry
from app.domains.analytics.schemas import (
    StrategyVersionComparisonResponse,
    StrategyVersionEntry,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger(__name__)


class StrategyVersionTracker:
    """Tracks and compares strategy versions across time based on trade journal data."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()

    def get_version_history(
        self,
        db: Session,
        strategy_id: str,
        portfolio_id: uuid.UUID | None = None,
    ) -> StrategyVersionComparisonResponse:
        """Get performance comparison across all versions of a strategy."""
        stmt = select(TradeJournalEntry).where(TradeJournalEntry.strategy_id == strategy_id)
        if portfolio_id:
            stmt = stmt.where(TradeJournalEntry.portfolio_id == portfolio_id)
        stmt = stmt.order_by(TradeJournalEntry.exit_timestamp)

        trades = list(db.execute(stmt).scalars().all())

        version_trades: dict[str, list[TradeJournalEntry]] = defaultdict(list)
        for t in trades:
            version_trades[t.strategy_version].append(t)

        versions: list[StrategyVersionEntry] = []
        for ver, vtrades in sorted(version_trades.items()):
            count = len(vtrades)
            winners = len([t for t in vtrades if t.net_pnl > 0])
            win_rate = (winners / count * 100.0) if count > 0 else 0.0
            net_pnl = sum(t.net_pnl for t in vtrades)
            turnover = sum(t.entry_price * t.quantity for t in vtrades)
            net_return = float(net_pnl / turnover * 100) if turnover > 0 else 0.0

            first_trade = vtrades[0].entry_timestamp if vtrades else None
            last_trade = vtrades[-1].exit_timestamp if vtrades else None

            sample_snapshot = vtrades[0].config_snapshot if vtrades else {}
            sample_param_id = vtrades[0].parameter_snapshot_id if vtrades else None

            versions.append(StrategyVersionEntry(
                strategy_id=strategy_id,
                strategy_version=ver,
                parameter_snapshot_id=sample_param_id,
                config_snapshot=sample_snapshot,
                trade_count=count,
                win_rate_pct=round(win_rate, 2),
                net_return_pct=round(net_return, 4),
                net_pnl=net_pnl,
                first_trade=first_trade,
                last_trade=last_trade,
            ))

        return StrategyVersionComparisonResponse(
            strategy_id=strategy_id,
            versions=versions,
        )
