"""Audit log service for storing and querying immutable domain events."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.trading.events import DomainEvent
from app.domains.trading.models import OrderEventLog


class AuditLogService:
    """Stores and retrieves immutable domain events for audit and replay."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record_event(self, event: DomainEvent) -> OrderEventLog:
        """Persist domain event to audit stream."""
        log_entry = OrderEventLog(
            event_id=event.event_id,
            aggregate_id=event.aggregate_id,
            aggregate_version=event.aggregate_version,
            event_version=event.event_version,
            event_type=event.event_type,
            timestamp=event.timestamp,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            payload=event.payload,
        )
        self._db.add(log_entry)
        self._db.flush()
        return log_entry

    def get_events_for_aggregate(self, aggregate_id: uuid.UUID) -> list[OrderEventLog]:
        """Fetch all chronological events for an aggregate entity."""
        stmt = (
            select(OrderEventLog)
            .where(OrderEventLog.aggregate_id == aggregate_id)
            .order_by(OrderEventLog.aggregate_version.asc(), OrderEventLog.timestamp.asc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_events_for_correlation(self, correlation_id: uuid.UUID) -> list[OrderEventLog]:
        """Fetch all events linked to a correlation ID (e.g. single trade action flow)."""
        stmt = (
            select(OrderEventLog)
            .where(OrderEventLog.correlation_id == correlation_id)
            .order_by(OrderEventLog.timestamp.asc())
        )
        return list(self._db.execute(stmt).scalars().all())
