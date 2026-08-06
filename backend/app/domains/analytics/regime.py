"""Market Regime Analysis Engine — Classify trades by market regime and measure regime-specific performance."""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.analytics.enums import MarketRegimeClassification
from app.domains.analytics.models import TradeJournalEntry
from app.domains.analytics.schemas import (
    RegimePerformanceEntry,
    RegimeStatisticsResponse,
)
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger(__name__)


class MarketRegimeAnalyzer:
    """Classifies trades by market regime and computes regime-specific strategy performance."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()

    @staticmethod
    def classify_regime(
        volatility: float = 0.0,
        trend_strength: float = 0.0,
        direction: float = 0.0,
    ) -> MarketRegimeClassification:
        """Classify market regime from quantitative indicators.

        Args:
            volatility: Normalized volatility (0-1 scale, higher = more volatile).
            trend_strength: ADX-like trend strength (0-1 scale).
            direction: Directional bias (-1 bearish to +1 bullish).
        """
        if volatility > 0.7:
            return MarketRegimeClassification.high_volatility
        if volatility < 0.3:
            return MarketRegimeClassification.low_volatility
        if trend_strength > 0.5:
            if direction > 0.2:
                return MarketRegimeClassification.bullish
            elif direction < -0.2:
                return MarketRegimeClassification.bearish
            return MarketRegimeClassification.trending
        return MarketRegimeClassification.sideways

    def get_regime_statistics(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> RegimeStatisticsResponse:
        """Compute aggregate performance per market regime."""
        trades = self._journal.get_all_portfolio_trades(db, portfolio_id)
        regime_groups = self._group_by_regime(trades)
        regime_stats = [self._compute_regime_entry(regime, group) for regime, group in regime_groups.items()]

        # Regime distribution
        total = len(trades) or 1
        distribution = {r: round(len(g) / total * 100, 2) for r, g in regime_groups.items()}

        # Strategy-regime cross-tabulation
        strategy_regime_matrix = self._build_strategy_regime_matrix(trades)

        return RegimeStatisticsResponse(
            portfolio_id=portfolio_id,
            regime_stats=regime_stats,
            strategy_regime_matrix=strategy_regime_matrix,
            regime_distribution=distribution,
        )

    def _group_by_regime(
        self,
        trades: list[TradeJournalEntry],
    ) -> dict[str, list[TradeJournalEntry]]:
        """Group trades by their market regime."""
        groups: dict[str, list[TradeJournalEntry]] = defaultdict(list)
        for t in trades:
            groups[t.market_regime].append(t)
        return groups

    def _compute_regime_entry(
        self,
        regime: str,
        trades: list[TradeJournalEntry],
    ) -> RegimePerformanceEntry:
        """Compute performance metrics for a single regime group."""
        count = len(trades)
        winners = len([t for t in trades if t.net_pnl > 0])
        win_rate = (winners / count * 100.0) if count > 0 else 0.0
        total_pnl = sum(t.net_pnl for t in trades)
        avg_return = float(sum(t.net_return_pct for t in trades) / count) if count > 0 else 0.0

        return RegimePerformanceEntry(
            regime=regime,
            trade_count=count,
            win_rate_pct=round(win_rate, 2),
            avg_return_pct=round(avg_return, 4),
            total_pnl=total_pnl,
        )

    def _build_strategy_regime_matrix(
        self,
        trades: list[TradeJournalEntry],
    ) -> dict[str, list[RegimePerformanceEntry]]:
        """Build a strategy × regime cross-tabulation matrix."""
        matrix: dict[str, dict[str, list[TradeJournalEntry]]] = defaultdict(lambda: defaultdict(list))
        for t in trades:
            matrix[t.strategy_id][t.market_regime].append(t)

        result: dict[str, list[RegimePerformanceEntry]] = {}
        for strategy_id, regime_map in matrix.items():
            result[strategy_id] = [
                self._compute_regime_entry(regime, group)
                for regime, group in regime_map.items()
            ]
        return result
