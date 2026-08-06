"""Portfolio Risk Analytics Engine — Exposure, concentration, correlation, and position distribution analysis."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.analytics.schemas import ExposureEntry, PortfolioRiskAnalytics
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.enums import PositionStatus
from app.domains.trading.models import Portfolio, Position

log = get_structured_logger(__name__)


class PortfolioRiskAnalyticsService:
    """Computes portfolio exposure, concentration, and risk distribution analytics."""

    def __init__(self) -> None:
        self._journal = TradeJournalService()

    def get_portfolio_risk_analytics(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        sector_mappings: dict[uuid.UUID, str] | None = None,
        strategy_mappings: dict[uuid.UUID, str] | None = None,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
    ) -> PortfolioRiskAnalytics:
        """Compute comprehensive risk analytics snapshot."""
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            return PortfolioRiskAnalytics(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(timezone.utc),
            )

        positions = list(
            db.execute(
                select(Position).where(
                    Position.portfolio_id == portfolio_id,
                    Position.status == PositionStatus.open,
                )
            ).scalars().all()
        )

        prices = current_prices or {}
        sectors = sector_mappings or {}

        # Calculate position market values
        position_values: list[tuple[Position, Decimal]] = []
        total_invested = Decimal("0.0000")
        for pos in positions:
            price = prices.get(pos.instrument_id, pos.current_price)
            mv = pos.quantity * price
            position_values.append((pos, mv))
            total_invested += mv

        total_equity = portfolio.cash_balance + portfolio.reserved_cash + total_invested

        # Sector exposure
        sector_values: dict[str, Decimal] = defaultdict(Decimal)
        sector_pnl: dict[str, Decimal] = defaultdict(Decimal)
        for pos, mv in position_values:
            sector = sectors.get(pos.instrument_id, "Unknown")
            sector_values[sector] += mv
            sector_pnl[sector] += pos.unrealized_pnl
        sector_exposure = [
            ExposureEntry(
                name=s,
                market_value=v,
                weight_pct=round(float(v / total_equity * 100), 2) if total_equity > 0 else 0.0,
                pnl=sector_pnl[s],
            )
            for s, v in sorted(sector_values.items(), key=lambda x: x[1], reverse=True)
        ]

        # Symbol exposure
        symbol_exposure = [
            ExposureEntry(
                name=f"inst_{pos.instrument_id.hex[:8]}",
                market_value=mv,
                weight_pct=round(float(mv / total_equity * 100), 2) if total_equity > 0 else 0.0,
                pnl=pos.unrealized_pnl,
            )
            for pos, mv in sorted(position_values, key=lambda x: x[1], reverse=True)
        ]

        # Strategy exposure (from trade journal)
        strategy_expo = self._compute_strategy_exposure(db, portfolio_id, total_equity)

        # Cash utilization
        cash_util = round(float(total_invested / total_equity * 100), 2) if total_equity > 0 else 0.0
        capital_util = round(float(total_invested / portfolio.initial_capital * 100), 2) if portfolio.initial_capital > 0 else 0.0

        # Concentration (HHI)
        weights = [float(mv / total_equity) for _, mv in position_values] if total_equity > 0 else []
        hhi = sum(w ** 2 for w in weights) * 10000 if weights else 0.0
        sorted_weights = sorted(weights, reverse=True)
        top_5_conc = sum(sorted_weights[:5]) * 100 if sorted_weights else 0.0

        # Position size distribution
        size_dist = self._compute_size_distribution(position_values, total_equity)

        return PortfolioRiskAnalytics(
            portfolio_id=portfolio_id,
            timestamp=datetime.now(timezone.utc),
            sector_exposure=sector_exposure,
            symbol_exposure=symbol_exposure,
            strategy_exposure=strategy_expo,
            cash_utilization_pct=cash_util,
            capital_utilization_pct=capital_util,
            concentration_hhi=round(hhi, 2),
            top_5_concentration_pct=round(top_5_conc, 2),
            position_count=len(positions),
            position_size_distribution=size_dist,
        )

    def _compute_strategy_exposure(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        total_equity: Decimal,
    ) -> list[ExposureEntry]:
        """Compute strategy-level capital allocation from trade journal."""
        strategies = self._journal.get_distinct_strategies(db, portfolio_id)
        entries = []
        for sid in strategies:
            trades = self._journal.get_strategy_trades(db, portfolio_id, sid)
            total_pnl = sum(t.net_pnl for t in trades)
            total_invested = sum(t.entry_price * t.quantity for t in trades)
            entries.append(ExposureEntry(
                name=sid,
                market_value=total_invested,
                weight_pct=round(float(total_invested / total_equity * 100), 2) if total_equity > 0 else 0.0,
                pnl=total_pnl,
            ))
        return sorted(entries, key=lambda e: e.market_value, reverse=True)

    @staticmethod
    def _compute_size_distribution(
        position_values: list[tuple[Any, Decimal]],
        total_equity: Decimal,
    ) -> dict[str, int]:
        """Categorize positions by size bucket."""
        buckets: dict[str, int] = {
            "0-2%": 0, "2-5%": 0, "5-10%": 0, "10-20%": 0, "20%+": 0,
        }
        for _, mv in position_values:
            pct = float(mv / total_equity * 100) if total_equity > 0 else 0.0
            if pct < 2:
                buckets["0-2%"] += 1
            elif pct < 5:
                buckets["2-5%"] += 1
            elif pct < 10:
                buckets["5-10%"] += 1
            elif pct < 20:
                buckets["10-20%"] += 1
            else:
                buckets["20%+"] += 1
        return buckets
