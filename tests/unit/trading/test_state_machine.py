"""Unit tests for OrderStateMachine."""
import uuid
from decimal import Decimal
import pytest

from app.domains.trading.enums import OrderSide, OrderStatus, OrderType
from app.domains.trading.exceptions import InvalidStateTransitionError
from app.domains.trading.models import Order
from app.domains.trading.state_machine import (
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    OrderStateMachine,
)


def _make_dummy_order(status: OrderStatus = OrderStatus.created) -> Order:
    return Order(
        portfolio_id=uuid.uuid4(),
        instrument_id=uuid.uuid4(),
        side=OrderSide.buy,
        order_type=OrderType.market,
        quantity=Decimal("100.0000"),
        status=status,
        version=1,
    )


def test_allowed_lifecycle_progression():
    order = _make_dummy_order(OrderStatus.created)
    assert OrderStateMachine.can_transition(order.status, OrderStatus.validated)

    OrderStateMachine.transition(order, OrderStatus.validated)
    assert order.status == OrderStatus.validated
    assert order.version == 2

    OrderStateMachine.transition(order, OrderStatus.accepted)
    assert order.status == OrderStatus.accepted
    assert order.version == 3

    OrderStateMachine.transition(order, OrderStatus.pending)
    assert order.status == OrderStatus.pending
    assert order.version == 4

    OrderStateMachine.transition(order, OrderStatus.partial)
    assert order.status == OrderStatus.partial
    assert order.version == 5

    OrderStateMachine.transition(order, OrderStatus.filled)
    assert order.status == OrderStatus.filled
    assert order.version == 6


def test_rejection_from_created_and_validated():
    order1 = _make_dummy_order(OrderStatus.created)
    OrderStateMachine.transition(order1, OrderStatus.rejected, reason="Risk limit exceeded")
    assert order1.status == OrderStatus.rejected
    assert order1.rejected_reason == "Risk limit exceeded"

    order2 = _make_dummy_order(OrderStatus.created)
    OrderStateMachine.transition(order2, OrderStatus.validated)
    OrderStateMachine.transition(order2, OrderStatus.rejected, reason="Post-val check failed")
    assert order2.status == OrderStatus.rejected


def test_cancellation_progression():
    for status in (OrderStatus.accepted, OrderStatus.pending, OrderStatus.partial):
        order = _make_dummy_order(status)
        assert OrderStateMachine.is_cancellable(order.status)
        OrderStateMachine.transition(order, OrderStatus.cancelled, reason="Cancelled by user")
        assert order.status == OrderStatus.cancelled


def test_illegal_state_transitions():
    order = _make_dummy_order(OrderStatus.created)
    with pytest.raises(InvalidStateTransitionError):
        OrderStateMachine.transition(order, OrderStatus.filled)

    with pytest.raises(InvalidStateTransitionError):
        OrderStateMachine.transition(order, OrderStatus.pending)

    order_filled = _make_dummy_order(OrderStatus.filled)
    assert OrderStateMachine.is_terminal(order_filled.status)
    with pytest.raises(InvalidStateTransitionError):
        OrderStateMachine.transition(order_filled, OrderStatus.cancelled)


def test_terminal_statuses():
    for term in TERMINAL_STATUSES:
        assert OrderStateMachine.is_terminal(term)
        assert not OrderStateMachine.can_transition(term, OrderStatus.pending)
        assert not OrderStateMachine.can_transition(term, OrderStatus.filled)
