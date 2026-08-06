"""Institutional Trade Journal Engine — Immutable round-trip trade recording with full cost decomposition."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session

from app.domains.analytics.enums import ExitReason
from app.domains.analytics.models import TradeJournalEntry
from app.domains.analytics.schemas import (
    DetailedCostBreakdown,
    TradeJournalEntryResponse,
    TradeJournalExportResponse,
    TradeJournalFilterRequest,
)
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger(__name__)

DEC_4DP = Decimal("0.0001")


def _q(val: Decimal) -> Decimal:
    return val.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


class TradeJournalService:
    """Records and queries immutable round-trip trade entries with full cost decomposition."""

    def record_trade(
        self,
        db: Session,
        *,
        portfolio_id: uuid.UUID,
        instrument_id: uuid.UUID,
        strategy_id: str,
        strategy_version: str = "1.0.0",
        parameter_snapshot_id: uuid.UUID | None = None,
        symbol: str,
        sector: str | None = None,
        entry_timestamp: datetime,
        exit_timestamp: datetime,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        position_size_pct: Decimal = Decimal("0.0000"),
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        exit_reason: ExitReason = ExitReason.unknown,
        signal_confidence: Decimal = Decimal("0.0000"),
        mfe: Decimal = Decimal("0.0000"),
        mae: Decimal = Decimal("0.0000"),
        cost_breakdown: dict[str, Any] | None = None,
        cost_profile_version: str = "default",
        market_regime: str = "unknown",
        portfolio_snapshot_id: uuid.UUID | None = None,
        entry_order_id: uuid.UUID | None = None,
        exit_order_id: uuid.UUID | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> TradeJournalEntry:
        """Create an immutable trade journal entry with derived P&L fields."""
        holding_seconds = int((exit_timestamp - entry_timestamp).total_seconds())
        turnover = quantity * entry_price

        # Gross P&L (before costs)
        gross_pnl = _q((exit_price - entry_price) * quantity)
        gross_return_pct = _q(((exit_price - entry_price) / entry_price) * Decimal("100")) if entry_price > 0 else Decimal("0.0000")

        # Total costs from breakdown
        costs = cost_breakdown or {}
        total_charges = Decimal(str(costs.get("total_charges", "0.0000")))
        net_pnl = _q(gross_pnl - total_charges)
        net_return_pct = _q(gross_return_pct - (total_charges / turnover * Decimal("100"))) if turnover > 0 else Decimal("0.0000")

        # Risk/reward ratio
        risk_reward_ratio: Decimal | None = None
        if stop_loss is not None and take_profit is not None and stop_loss != entry_price:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            risk_reward_ratio = _q(reward / risk) if risk > 0 else None

        trade_id = f"TJ-{uuid.uuid4().hex[:12].upper()}"

        entry = TradeJournalEntry(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            trade_id=trade_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            parameter_snapshot_id=parameter_snapshot_id,
            symbol=symbol,
            sector=sector,
            entry_timestamp=entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            position_size_pct=position_size_pct,
            holding_duration_seconds=holding_seconds,
            stop_loss=stop_loss,
            take_profit=take_profit,
            exit_reason=exit_reason,
            signal_confidence=signal_confidence,
            risk_reward_ratio=risk_reward_ratio,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            gross_return_pct=gross_return_pct,
            net_return_pct=net_return_pct,
            mfe=mfe,
            mae=mae,
            cost_breakdown=costs,
            cost_profile_version=cost_profile_version,
            market_regime=market_regime,
            portfolio_snapshot_id=portfolio_snapshot_id,
            entry_order_id=entry_order_id,
            exit_order_id=exit_order_id,
            config_snapshot=config_snapshot or {},
        )
        db.add(entry)
        db.flush()

        log.info(
            "trade_journal_recorded",
            trade_id=trade_id,
            strategy=strategy_id,
            symbol=symbol,
            gross_pnl=str(gross_pnl),
            net_pnl=str(net_pnl),
        )
        return entry

    def get_trades(
        self,
        db: Session,
        filters: TradeJournalFilterRequest,
    ) -> list[TradeJournalEntry]:
        """Query trade journal entries with filters."""
        stmt = select(TradeJournalEntry).where(
            TradeJournalEntry.portfolio_id == filters.portfolio_id
        )

        if filters.start_date:
            stmt = stmt.where(TradeJournalEntry.entry_timestamp >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(TradeJournalEntry.exit_timestamp <= filters.end_date)
        if filters.strategy_id:
            stmt = stmt.where(TradeJournalEntry.strategy_id == filters.strategy_id)
        if filters.symbol:
            stmt = stmt.where(TradeJournalEntry.symbol == filters.symbol)
        if filters.exit_reason:
            stmt = stmt.where(TradeJournalEntry.exit_reason == filters.exit_reason)
        if filters.min_return_pct is not None:
            stmt = stmt.where(TradeJournalEntry.net_return_pct >= filters.min_return_pct)
        if filters.max_return_pct is not None:
            stmt = stmt.where(TradeJournalEntry.net_return_pct <= filters.max_return_pct)
        if filters.market_regime:
            stmt = stmt.where(TradeJournalEntry.market_regime == filters.market_regime)

        stmt = stmt.order_by(desc(TradeJournalEntry.exit_timestamp))
        stmt = stmt.offset(filters.offset).limit(filters.limit)

        return list(db.execute(stmt).scalars().all())

    def get_trade_by_id(self, db: Session, trade_id: str) -> TradeJournalEntry | None:
        """Fetch a single trade journal entry."""
        stmt = select(TradeJournalEntry).where(TradeJournalEntry.trade_id == trade_id)
        return db.execute(stmt).scalar_one_or_none()

    def export_trades(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> TradeJournalExportResponse:
        """Export all trades for a portfolio within a date range."""
        filters = TradeJournalFilterRequest(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000,
        )
        trades = self.get_trades(db, filters)
        return TradeJournalExportResponse(
            portfolio_id=portfolio_id,
            total_trades=len(trades),
            export_timestamp=datetime.now(timezone.utc),
            trades=[TradeJournalEntryResponse.model_validate(t) for t in trades],
        )

    def get_all_portfolio_trades(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
    ) -> list[TradeJournalEntry]:
        """Fetch all trade journal entries for a portfolio ordered by exit timestamp."""
        stmt = (
            select(TradeJournalEntry)
            .where(TradeJournalEntry.portfolio_id == portfolio_id)
            .order_by(TradeJournalEntry.exit_timestamp)
        )
        return list(db.execute(stmt).scalars().all())

    def get_strategy_trades(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        strategy_id: str,
    ) -> list[TradeJournalEntry]:
        """Fetch all trades for a specific strategy in a portfolio."""
        stmt = (
            select(TradeJournalEntry)
            .where(
                and_(
                    TradeJournalEntry.portfolio_id == portfolio_id,
                    TradeJournalEntry.strategy_id == strategy_id,
                )
            )
            .order_by(TradeJournalEntry.exit_timestamp)
        )
        return list(db.execute(stmt).scalars().all())

    def get_distinct_strategies(self, db: Session, portfolio_id: uuid.UUID) -> list[str]:
        """Get all distinct strategy IDs that have trades in a portfolio."""
        stmt = (
            select(TradeJournalEntry.strategy_id)
            .where(TradeJournalEntry.portfolio_id == portfolio_id)
            .distinct()
        )
        return list(db.execute(stmt).scalars().all())
