"""Unit tests for the internal in-process Event Bus."""
from datetime import datetime, timezone
import uuid
import pytest

from app.domains.orchestrator.enums import EventType
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.events import (
    BaseOrchestratorEvent,
    MarketDataUpdatedEvent,
    OrderSubmittedEvent,
)


def test_event_bus_subscribe_and_publish():
    bus = EventBus()
    received = []

    def handle_md(evt: BaseOrchestratorEvent):
        received.append(evt)

    bus.subscribe(EventType.market_data_updated, handle_md)

    event = MarketDataUpdatedEvent(
        instrument_count=10,
        latest_timestamp=datetime.now(timezone.utc),
    )
    bus.publish(event)

    assert len(received) == 1
    assert received[0].event_type == EventType.market_data_updated
    assert isinstance(received[0], MarketDataUpdatedEvent)
    assert received[0].instrument_count == 10


def test_event_bus_global_subscriber():
    bus = EventBus()
    all_events = []

    bus.subscribe(None, lambda e: all_events.append(e))

    evt1 = MarketDataUpdatedEvent(instrument_count=5, latest_timestamp=datetime.now(timezone.utc))
    evt2 = OrderSubmittedEvent(
        order_id=uuid.uuid4(),
        portfolio_id=uuid.uuid4(),
        instrument_id=uuid.uuid4(),
        symbol="TCS",
        side="buy",
        quantity=10,
        order_type="market",
    )

    bus.publish(evt1)
    bus.publish(evt2)

    assert len(all_events) == 2


def test_event_bus_subscriber_error_isolation():
    bus = EventBus()
    success_received = []

    def failing_handler(evt):
        raise RuntimeError("Subscriber explosion")

    def successful_handler(evt):
        success_received.append(evt)

    bus.subscribe(EventType.market_data_updated, failing_handler)
    bus.subscribe(EventType.market_data_updated, successful_handler)

    evt = MarketDataUpdatedEvent(instrument_count=1, latest_timestamp=datetime.now(timezone.utc))
    # Should not raise exception and successful_handler must be invoked
    bus.publish(evt)

    assert len(success_received) == 1


def test_event_bus_history_and_clear():
    bus = EventBus(max_history=5)
    for i in range(10):
        evt = MarketDataUpdatedEvent(instrument_count=i, latest_timestamp=datetime.now(timezone.utc))
        bus.publish(evt)

    history = bus.get_history()
    assert len(history) == 5
    assert history[0].instrument_count == 9  # Most recent first

    bus.clear()
    assert len(bus.get_history()) == 0
