"""Append-only double-entry cash ledger service with row-level locking."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.trading.enums import TxnType
from app.domains.trading.events import (
    CashReleasedEvent,
    CashReservedEvent,
    LedgerEntryCreatedEvent,
)
from app.domains.trading.exceptions import (
    InsufficientBuyingPowerError,
    LedgerReconciliationError,
    PortfolioNotFoundError,
)
from app.domains.trading.models import Portfolio, Transaction


class LedgerService:
    """Manages immutable cash transactions, buying power reservations, and reconciliations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_portfolio_locked(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Fetch portfolio with row-level lock (with_for_update) for write safety."""
        # SQLite doesn't support with_for_update natively, SQLAlchemy handles this gracefully
        stmt = select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
        portfolio = self._db.execute(stmt).scalar_one_or_none()
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        return portfolio

    def record_transaction(
        self,
        portfolio_id: uuid.UUID,
        txn_type: TxnType,
        amount: Decimal,
        related_order_id: uuid.UUID | None = None,
        related_fill_id: uuid.UUID | None = None,
        reference_type: str | None = None,
        description: str | None = None,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> tuple[Transaction, LedgerEntryCreatedEvent]:
        """Record an immutable ledger entry and atomically adjust cash balance."""
        portfolio = self._get_portfolio_locked(portfolio_id)

        new_balance = portfolio.cash_balance + amount
        portfolio.cash_balance = new_balance
        portfolio.version += 1

        txn = Transaction(
            portfolio_id=portfolio.id,
            txn_type=txn_type,
            amount=amount,
            balance_after=new_balance,
            related_order_id=related_order_id,
            related_fill_id=related_fill_id,
            reference_type=reference_type,
            description=description,
        )
        self._db.add(txn)
        self._db.flush()

        event = LedgerEntryCreatedEvent(
            aggregate_id=portfolio.id,
            aggregate_version=portfolio.version,
            correlation_id=correlation_id or uuid.uuid4(),
            causation_id=causation_id,
            payload={
                "transaction_id": str(txn.id),
                "portfolio_id": str(portfolio.id),
                "txn_type": txn_type.value,
                "amount": str(amount),
                "balance_after": str(new_balance),
                "related_order_id": str(related_order_id) if related_order_id else None,
                "related_fill_id": str(related_fill_id) if related_fill_id else None,
            },
        )
        return txn, event

    def reserve_buying_power(
        self,
        portfolio_id: uuid.UUID,
        amount: Decimal,
        order_id: uuid.UUID,
        correlation_id: uuid.UUID | None = None,
    ) -> CashReservedEvent:
        """Block cash for an open buy order."""
        portfolio = self._get_portfolio_locked(portfolio_id)
        available = portfolio.cash_balance - portfolio.reserved_cash
        if amount > available:
            raise InsufficientBuyingPowerError(portfolio.id, required=amount, available=available)

        portfolio.reserved_cash += amount
        portfolio.version += 1
        self._db.flush()

        return CashReservedEvent(
            aggregate_id=portfolio.id,
            aggregate_version=portfolio.version,
            correlation_id=correlation_id or uuid.uuid4(),
            payload={
                "portfolio_id": str(portfolio.id),
                "order_id": str(order_id),
                "reserved_amount": str(amount),
                "total_reserved": str(portfolio.reserved_cash),
                "available_buying_power": str(portfolio.cash_balance - portfolio.reserved_cash),
            },
        )

    def release_buying_power(
        self,
        portfolio_id: uuid.UUID,
        amount: Decimal,
        order_id: uuid.UUID,
        correlation_id: uuid.UUID | None = None,
    ) -> CashReleasedEvent:
        """Release previously reserved cash on fill or cancellation."""
        portfolio = self._get_portfolio_locked(portfolio_id)
        release_qty = min(amount, portfolio.reserved_cash)
        portfolio.reserved_cash -= release_qty
        portfolio.version += 1
        self._db.flush()

        return CashReleasedEvent(
            aggregate_id=portfolio.id,
            aggregate_version=portfolio.version,
            correlation_id=correlation_id or uuid.uuid4(),
            payload={
                "portfolio_id": str(portfolio.id),
                "order_id": str(order_id),
                "released_amount": str(release_qty),
                "total_reserved": str(portfolio.reserved_cash),
                "available_buying_power": str(portfolio.cash_balance - portfolio.reserved_cash),
            },
        )

    def reconcile_balance(self, portfolio_id: uuid.UUID) -> bool:
        """Verify that portfolio cash_balance exactly equals sum(transactions)."""
        portfolio = self._get_portfolio_locked(portfolio_id)
        ledger_sum = self._db.execute(
            select(func.coalesce(func.sum(Transaction.amount), Decimal("0.0000")))
            .where(Transaction.portfolio_id == portfolio_id)
        ).scalar_one()

        if ledger_sum != portfolio.cash_balance:
            raise LedgerReconciliationError(
                portfolio_id=portfolio.id,
                ledger_sum=ledger_sum,
                cash_balance=portfolio.cash_balance,
            )
        return True
