"""Strategy Attribution Engine — Per-strategy performance measurement and leaderboard ranking."""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.analytics.schemas import (
    StrategyAttributionReport,
    StrategyLeaderboardEntry,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.analytics.models import TradeJournalEntry
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger(__name__)


class StrategyAttributionService:
    """Measures every strategy independently: win rate, return, attribution, and leaderboard."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()

    def get_strategy_attribution(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        strategy_id: str,
    ) -> StrategyAttributionReport:
        """Compute comprehensive attribution for a single strategy."""
        trades = self._journal.get_strategy_trades(db, portfolio_id, strategy_id)
        return self._build_attribution(trades, portfolio_id, db)

    def get_all_strategy_attributions(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[StrategyAttributionReport]:
        """Compute attribution for all strategies in a portfolio."""
        strategy_ids = self._journal.get_distinct_strategies(db, portfolio_id)
        return [
            self.get_strategy_attribution(db, portfolio_id, sid)
            for sid in strategy_ids
        ]

    def get_strategy_leaderboard(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[StrategyLeaderboardEntry]:
        """Rank strategies by net return."""
        attributions = self.get_all_strategy_attributions(db, portfolio_id)
        sorted_attrs = sorted(attributions, key=lambda a: a.net_return_pct, reverse=True)

        all_trades = self._journal.get_all_portfolio_trades(db, portfolio_id)
        total_net_pnl = sum(float(t.net_pnl) for t in all_trades) or 1.0

        entries = []
        for rank, attr in enumerate(sorted_attrs, 1):
            contribution = (float(attr.net_pnl) / total_net_pnl * 100.0) if total_net_pnl != 0 else 0.0
            entries.append(StrategyLeaderboardEntry(
                rank=rank,
                strategy_id=attr.strategy_id,
                total_trades=attr.total_trades,
                win_rate_pct=attr.win_rate_pct,
                net_return_pct=attr.net_return_pct,
                net_pnl=attr.net_pnl,
                sharpe_ratio=attr.sharpe_ratio,
                profit_factor=attr.profit_factor,
                portfolio_contribution_pct=round(contribution, 2),
            ))
        return entries

    def _build_attribution(
        self,
        trades: list[TradeJournalEntry],
        portfolio_id: uuid.UUID,
        db: Session,
    ) -> StrategyAttributionReport:
        """Build a complete attribution report from trade entries."""
        if not trades:
            return StrategyAttributionReport(strategy_id="", strategy_version="")

        strategy_id = trades[0].strategy_id
        strategy_version = trades[0].strategy_version

        total = len(trades)
        winners = [t for t in trades if t.gross_pnl > 0]
        losers = [t for t in trades if t.gross_pnl <= 0]
        win_rate = (len(winners) / total * 100.0) if total > 0 else 0.0

        gross_pnl = sum(t.gross_pnl for t in trades)
        net_pnl = sum(t.net_pnl for t in trades)

        avg_entry = sum(float(t.entry_price) * float(t.quantity) for t in trades)
        gross_return_pct = (float(gross_pnl) / avg_entry * 100.0) if avg_entry > 0 else 0.0
        net_return_pct = (float(net_pnl) / avg_entry * 100.0) if avg_entry > 0 else 0.0

        avg_holding = int(sum(t.holding_duration_seconds for t in trades) / total) if total > 0 else 0

        # Symbol performance
        symbol_pnl: dict[str, float] = defaultdict(float)
        for t in trades:
            symbol_pnl[t.symbol] += float(t.net_pnl)
        sorted_symbols = sorted(symbol_pnl.items(), key=lambda x: x[1], reverse=True)
        best_symbols = [{"symbol": s, "net_pnl": round(p, 2)} for s, p in sorted_symbols[:5]]
        worst_symbols = [{"symbol": s, "net_pnl": round(p, 2)} for s, p in sorted_symbols[-5:]]

        # Regime performance
        regime_trades: dict[str, list[TradeJournalEntry]] = defaultdict(list)
        for t in trades:
            regime_trades[t.market_regime].append(t)
        regime_perf: dict[str, dict[str, float]] = {}
        for regime, rtrades in regime_trades.items():
            rwin = len([t for t in rtrades if t.gross_pnl > 0])
            rcount = len(rtrades)
            regime_perf[regime] = {
                "trade_count": rcount,
                "win_rate_pct": round(rwin / rcount * 100, 2) if rcount > 0 else 0.0,
                "total_pnl": round(float(sum(t.net_pnl for t in rtrades)), 2),
            }

        # Profit factor
        gross_profit = float(sum(t.gross_pnl for t in winners))
        gross_loss = abs(float(sum(t.gross_pnl for t in losers)))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (10.0 if gross_profit > 0 else 0.0)

        # Portfolio contribution
        all_trades = self._journal.get_all_portfolio_trades(db, portfolio_id)
        total_portfolio_pnl = float(sum(t.net_pnl for t in all_trades)) or 1.0
        contribution = float(net_pnl) / total_portfolio_pnl * 100.0 if total_portfolio_pnl != 0 else 0.0

        return StrategyAttributionReport(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate_pct=round(win_rate, 2),
            gross_return_pct=round(gross_return_pct, 4),
            net_return_pct=round(net_return_pct, 4),
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            average_holding_seconds=avg_holding,
            best_symbols=best_symbols,
            worst_symbols=worst_symbols,
            regime_performance=regime_perf,
            portfolio_contribution_pct=round(contribution, 2),
            profit_factor=round(profit_factor, 2),
        )
