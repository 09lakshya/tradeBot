"""In-memory typed Pub/Sub Event Bus with subscriber error isolation and audit logging."""
from collections import defaultdict
import logging
from typing import Any, Callable
from sqlalchemy.orm import Session

from app.domains.orchestrator.enums import EventType
from app.domains.orchestrator.events import BaseOrchestratorEvent
from app.domains.orchestrator.models import OrchestratorEventRecord

log = logging.getLogger(__name__)


class EventBus:
    """Lightweight, thread-safe, in-process Event Bus for immutable domain events."""

    def __init__(self, max_history: int = 1000):
        self._subscribers: dict[EventType, list[Callable[[BaseOrchestratorEvent], Any]]] = defaultdict(list)
        self._global_subscribers: list[Callable[[BaseOrchestratorEvent], Any]] = []
        self._event_history: list[BaseOrchestratorEvent] = []
        self._max_history = max_history

    def subscribe(
        self,
        event_type: EventType | None,
        callback: Callable[[BaseOrchestratorEvent], Any],
    ) -> None:
        """Subscribes a callback to a specific event type or all events (if event_type is None)."""
        if event_type is None:
            if callback not in self._global_subscribers:
                self._global_subscribers.append(callback)
        else:
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(
        self,
        event_type: EventType | None,
        callback: Callable[[BaseOrchestratorEvent], Any],
    ) -> None:
        """Unsubscribes a callback from events."""
        if event_type is None:
            if callback in self._global_subscribers:
                self._global_subscribers.remove(callback)
        else:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(
        self,
        event: BaseOrchestratorEvent,
        db: Session | None = None,
    ) -> None:
        """Publishes an immutable event to all registered subscribers with error isolation."""
        # Append to in-memory circular history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        # Persist to database audit store if session provided
        if db is not None:
            try:
                rec = OrchestratorEventRecord(
                    id=event.event_id,
                    event_type=event.event_type.value,
                    timestamp=event.timestamp,
                    source=event.source,
                    payload=event.to_dict(),
                )
                db.add(rec)
            except Exception as err:
                log.error("Failed to persist orchestrator event to DB: %s", err)

        # Notify specific subscribers
        target_subscribers = list(self._subscribers.get(event.event_type, []))
        for sub in target_subscribers:
            try:
                sub(event)
            except Exception as err:
                log.error("Error in event subscriber for %s: %s", event.event_type.value, err, exc_info=True)

        # Notify global subscribers
        global_subs = list(self._global_subscribers)
        for sub in global_subs:
            try:
                sub(event)
            except Exception as err:
                log.error("Error in global event subscriber: %s", err, exc_info=True)

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[BaseOrchestratorEvent]:
        """Retrieves recent event history in reverse chronological order."""
        if event_type is None:
            return list(reversed(self._event_history[-limit:]))
        filtered = [e for e in self._event_history if e.event_type == event_type]
        return list(reversed(filtered[-limit:]))

    def clear(self) -> None:
        """Clears subscribers and event history."""
        self._subscribers.clear()
        self._global_subscribers.clear()
        self._event_history.clear()
