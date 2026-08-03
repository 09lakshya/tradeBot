"""Typed domain exceptions for the Trading domain."""
from __future__ import annotations

import uuid


class TradingDomainError(Exception):
    """Base domain exception for all trading operations."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidStateTransitionError(TradingDomainError):
    """Raised when an order transition violates the strict state machine."""

    def __init__(self, order_id: uuid.UUID, current_status: str, target_status: str) -> None:
        super().__init__(
            f"Cannot transition order {order_id} from '{current_status}' to '{target_status}'.",
            {"order_id": str(order_id), "current_status": current_status, "target_status": target_status},
        )
        self.order_id = order_id
        self.current_status = current_status
        self.target_status = target_status


class InsufficientBuyingPowerError(TradingDomainError):
    """Raised when available buying power cannot cover the required cash reservation."""

    def __init__(self, portfolio_id: uuid.UUID, required: object, available: object) -> None:
        super().__init__(
            f"Insufficient buying power in portfolio {portfolio_id}: required {required}, available {available}.",
            {"portfolio_id": str(portfolio_id), "required": str(required), "available": str(available)},
        )
        self.portfolio_id = portfolio_id
        self.required = required
        self.available = available


class DuplicateIdempotencyKeyError(TradingDomainError):
    """Raised when an order with the same idempotency key already exists."""

    def __init__(self, idempotency_key: str, existing_order_id: uuid.UUID) -> None:
        super().__init__(
            f"Order with idempotency key '{idempotency_key}' already exists (order {existing_order_id}).",
            {"idempotency_key": idempotency_key, "existing_order_id": str(existing_order_id)},
        )
        self.idempotency_key = idempotency_key
        self.existing_order_id = existing_order_id


class InvalidOrderQuantityError(TradingDomainError):
    """Raised when order quantity is non-positive or violates lot size."""

    def __init__(self, quantity: object, reason: str = "Quantity must be positive") -> None:
        super().__init__(
            f"Invalid order quantity '{quantity}': {reason}",
            {"quantity": str(quantity), "reason": reason},
        )
        self.quantity = quantity


class InvalidOrderPriceError(TradingDomainError):
    """Raised when order price is non-positive or missing for limit/stop orders."""

    def __init__(self, price: object, reason: str = "Price must be positive") -> None:
        super().__init__(
            f"Invalid order price '{price}': {reason}",
            {"price": str(price), "reason": reason},
        )
        self.price = price


class PortfolioNotFoundError(TradingDomainError):
    """Raised when a specified portfolio ID does not exist."""

    def __init__(self, portfolio_id: uuid.UUID) -> None:
        super().__init__(
            f"Portfolio {portfolio_id} not found.",
            {"portfolio_id": str(portfolio_id)},
        )
        self.portfolio_id = portfolio_id


class PositionNotFoundError(TradingDomainError):
    """Raised when a specified position is not found."""

    def __init__(self, portfolio_id: uuid.UUID, instrument_id: uuid.UUID) -> None:
        super().__init__(
            f"Position for instrument {instrument_id} in portfolio {portfolio_id} not found.",
            {"portfolio_id": str(portfolio_id), "instrument_id": str(instrument_id)},
        )
        self.portfolio_id = portfolio_id
        self.instrument_id = instrument_id


class InsufficientPositionQuantityError(TradingDomainError):
    """Raised when attempting to sell more shares than currently held."""

    def __init__(self, portfolio_id: uuid.UUID, instrument_id: uuid.UUID, requested: object, available: object) -> None:
        super().__init__(
            f"Cannot sell {requested} units of instrument {instrument_id}: only {available} available in portfolio {portfolio_id}.",
            {"portfolio_id": str(portfolio_id), "instrument_id": str(instrument_id), "requested": str(requested), "available": str(available)},
        )
        self.portfolio_id = portfolio_id
        self.instrument_id = instrument_id
        self.requested = requested
        self.available = available


class OrderNotFoundError(TradingDomainError):
    """Raised when a specified order ID does not exist."""

    def __init__(self, order_id: uuid.UUID) -> None:
        super().__init__(
            f"Order {order_id} not found.",
            {"order_id": str(order_id)},
        )
        self.order_id = order_id


class OrderNotCancellableError(TradingDomainError):
    """Raised when attempting to cancel an order that is already in a terminal state."""

    def __init__(self, order_id: uuid.UUID, current_status: str) -> None:
        super().__init__(
            f"Order {order_id} cannot be cancelled because it is in status '{current_status}'.",
            {"order_id": str(order_id), "current_status": current_status},
        )
        self.order_id = order_id
        self.current_status = current_status


class StaleAggregateVersionError(TradingDomainError):
    """Raised when optimistic concurrency check detects a version mismatch."""

    def __init__(self, aggregate_name: str, aggregate_id: uuid.UUID, expected: int, actual: int) -> None:
        super().__init__(
            f"Stale version for {aggregate_name} {aggregate_id}: expected {expected}, found {actual}.",
            {"aggregate_name": aggregate_name, "aggregate_id": str(aggregate_id), "expected_version": expected, "actual_version": actual},
        )
        self.aggregate_name = aggregate_name
        self.aggregate_id = aggregate_id
        self.expected = expected
        self.actual = actual


class LedgerReconciliationError(TradingDomainError):
    """Raised when the calculated sum of ledger transactions does not match portfolio cash balance."""

    def __init__(self, portfolio_id: uuid.UUID, ledger_sum: object, cash_balance: object) -> None:
        super().__init__(
            f"Ledger reconciliation mismatch for portfolio {portfolio_id}: ledger sum={ledger_sum}, cash_balance={cash_balance}.",
            {"portfolio_id": str(portfolio_id), "ledger_sum": str(ledger_sum), "cash_balance": str(cash_balance)},
        )
        self.portfolio_id = portfolio_id
        self.ledger_sum = ledger_sum
        self.cash_balance = cash_balance


class InstrumentNotFoundError(TradingDomainError):
    """Raised when an instrument is missing or not active for trading."""

    def __init__(self, instrument_id: uuid.UUID) -> None:
        super().__init__(
            f"Instrument {instrument_id} not found or inactive for trading.",
            {"instrument_id": str(instrument_id)},
        )
        self.instrument_id = instrument_id


class CostProfileNotFoundError(TradingDomainError):
    """Raised when a requested cost profile is not registered."""

    def __init__(self, profile_name: str) -> None:
        super().__init__(
            f"Cost profile '{profile_name}' not found.",
            {"profile_name": profile_name},
        )
        self.profile_name = profile_name
