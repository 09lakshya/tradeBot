"""Unit tests for the Clock abstraction and Domain Events."""
from datetime import UTC, datetime, timedelta
import uuid

import pytest

from app.domains.trading.clock import FixedClock, ReplayClock, SystemClock
from app.domains.trading.events import (
    OrderCreatedEvent,
    OrderFilledEvent,
    PositionOpenedEvent,
)
from app.domains.trading.exceptions import (
    InvalidStateTransitionError,
    InsufficientBuyingPowerError,
)


def test_system_clock():
    clock = SystemClock()
    t1 = clock.now()
    assert t1.tzinfo is not None
    assert isinstance(t1, datetime)


def test_fixed_clock():
    t0 = datetime(2026, 8, 1, 9, 15, 0, tzinfo=UTC)
    clock = FixedClock(t0)
    assert clock.now() == t0

    advanced = clock.advance(timedelta(minutes=15))
    assert advanced == datetime(2026, 8, 1, 9, 30, 0, tzinfo=UTC)
    assert clock.now() == datetime(2026, 8, 1, 9, 30, 0, tzinfo=UTC)

    new_t = datetime(2026, 8, 1, 15, 30, 0, tzinfo=UTC)
    clock.set_time(new_t)
    assert clock.now() == new_t


def test_replay_clock():
    t0 = datetime(2026, 8, 1, 9, 15, 0, tzinfo=UTC)
    clock = ReplayClock(t0)
    assert clock.now() == t0

    t1 = datetime(2026, 8, 1, 9, 30, 0, tzinfo=UTC)
    clock.step_to(t1)
    assert clock.now() == t1

    with pytest.raises(ValueError, match="cannot step backwards"):
        clock.step_to(datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC))


def test_domain_events():
    corr_id = uuid.uuid4()
    order_id = uuid.uuid4()
    evt = OrderCreatedEvent(
        aggregate_id=order_id,
        aggregate_version=1,
        correlation_id=corr_id,
        payload={"symbol": "INFY", "quantity": 100},
    )
    assert evt.event_type == "OrderCreated"
    assert evt.aggregate_id == order_id
    assert evt.correlation_id == corr_id
    json_str = evt.to_json()
    assert "OrderCreated" in json_str
    assert "INFY" in json_str


def test_domain_exceptions():
    order_id = uuid.uuid4()
    err = InvalidStateTransitionError(order_id, "pending", "validated")
    assert "Cannot transition order" in str(err)
    assert err.order_id == order_id
    assert err.current_status == "pending"
    assert err.target_status == "validated"

    port_id = uuid.uuid4()
    bp_err = InsufficientBuyingPowerError(port_id, "10000.00", "5000.00")
    assert "Insufficient buying power" in str(bp_err)
    assert bp_err.portfolio_id == port_id
