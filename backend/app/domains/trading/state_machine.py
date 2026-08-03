"""Order state machine enforcing strict lifecycle transitions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domains.trading.enums import OrderStatus
from app.domains.trading.exceptions import InvalidStateTransitionError

if TYPE_CHECKING:
    from app.domains.trading.models import Order


TRANSITION_MAP: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.created: {OrderStatus.validated, OrderStatus.rejected},
    OrderStatus.validated: {OrderStatus.accepted, OrderStatus.rejected},
    OrderStatus.accepted: {OrderStatus.pending, OrderStatus.cancelled},
    OrderStatus.pending: {
        OrderStatus.partial,
        OrderStatus.filled,
        OrderStatus.cancelled,
        OrderStatus.expired,
    },
    OrderStatus.partial: {
        OrderStatus.partial,
        OrderStatus.filled,
        OrderStatus.cancelled,
        OrderStatus.expired,
    },
    # Terminal states
    OrderStatus.filled: set(),
    OrderStatus.cancelled: set(),
    OrderStatus.rejected: set(),
    OrderStatus.expired: set(),
}

TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset({
    OrderStatus.filled,
    OrderStatus.cancelled,
    OrderStatus.rejected,
    OrderStatus.expired,
})

CANCELLABLE_STATUSES: frozenset[OrderStatus] = frozenset({
    OrderStatus.created,
    OrderStatus.validated,
    OrderStatus.accepted,
    OrderStatus.pending,
    OrderStatus.partial,
})

ACTIVE_STATUSES: frozenset[OrderStatus] = frozenset({
    OrderStatus.pending,
    OrderStatus.partial,
})


class OrderStateMachine:
    """Strict transition validator and transition executor for Orders."""

    @staticmethod
    def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
        """Check if transition is mathematically allowed."""
        return to_status in TRANSITION_MAP.get(from_status, set())

    @staticmethod
    def is_terminal(status: OrderStatus) -> bool:
        """Check if order status is a final terminal state."""
        return status in TERMINAL_STATUSES

    @staticmethod
    def is_cancellable(status: OrderStatus) -> bool:
        """Check if order can be cancelled."""
        return status in CANCELLABLE_STATUSES

    @staticmethod
    def is_active(status: OrderStatus) -> bool:
        """Check if order is currently active in the market/queue."""
        return status in ACTIVE_STATUSES

    @classmethod
    def validate_transition(cls, order: Order, to_status: OrderStatus) -> None:
        """Raise InvalidStateTransitionError if transition is illegal."""
        if not cls.can_transition(order.status, to_status):
            raise InvalidStateTransitionError(
                order_id=order.id,
                current_status=order.status.value,
                target_status=to_status.value,
            )

    @classmethod
    def transition(
        cls,
        order: Order,
        to_status: OrderStatus,
        reason: str | None = None,
    ) -> Order:
        """Execute state transition on order, incrementing its version."""
        cls.validate_transition(order, to_status)
        order.status = to_status
        order.version += 1
        if reason:
            order.rejected_reason = reason
        return order
