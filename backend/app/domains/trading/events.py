"""Domain events for the Trading domain.

Every financial or lifecycle change emits an immutable DomainEvent containing:
- event_id (UUID)
- aggregate_id (UUID)
- aggregate_version (int)
- event_version (int)
- timestamp (datetime UTC via Clock)
- correlation_id (UUID)
- causation_id (UUID | None)
- payload (dict)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def _json_serial(obj: Any) -> Any:
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, (uuid.UUID,)):
        return str(obj)
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _default_utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DomainEvent:
    """Base immutable domain event representation."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    aggregate_id: uuid.UUID = field(default_factory=uuid.uuid4)
    aggregate_version: int = 1
    event_version: int = 1
    event_type: str = "DomainEvent"
    timestamp: datetime = field(default_factory=_default_utc_now)
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    causation_id: uuid.UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=_json_serial)


@dataclass(frozen=True)
class OrderCreatedEvent(DomainEvent):
    event_type: str = "OrderCreated"


@dataclass(frozen=True)
class OrderValidatedEvent(DomainEvent):
    event_type: str = "OrderValidated"


@dataclass(frozen=True)
class OrderAcceptedEvent(DomainEvent):
    event_type: str = "OrderAccepted"


@dataclass(frozen=True)
class OrderPendingEvent(DomainEvent):
    event_type: str = "OrderPending"


@dataclass(frozen=True)
class OrderPartiallyFilledEvent(DomainEvent):
    event_type: str = "OrderPartiallyFilled"


@dataclass(frozen=True)
class OrderFilledEvent(DomainEvent):
    event_type: str = "OrderFilled"


@dataclass(frozen=True)
class OrderCancelledEvent(DomainEvent):
    event_type: str = "OrderCancelled"


@dataclass(frozen=True)
class OrderRejectedEvent(DomainEvent):
    event_type: str = "OrderRejected"


@dataclass(frozen=True)
class OrderExpiredEvent(DomainEvent):
    event_type: str = "OrderExpired"


@dataclass(frozen=True)
class PositionOpenedEvent(DomainEvent):
    event_type: str = "PositionOpened"


@dataclass(frozen=True)
class PositionUpdatedEvent(DomainEvent):
    event_type: str = "PositionUpdated"


@dataclass(frozen=True)
class PositionClosedEvent(DomainEvent):
    event_type: str = "PositionClosed"


@dataclass(frozen=True)
class CashReservedEvent(DomainEvent):
    event_type: str = "CashReserved"


@dataclass(frozen=True)
class CashReleasedEvent(DomainEvent):
    event_type: str = "CashReleased"


@dataclass(frozen=True)
class LedgerEntryCreatedEvent(DomainEvent):
    event_type: str = "LedgerEntryCreated"
