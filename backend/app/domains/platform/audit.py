"""Immutable, Append-Only Audit Trail Service."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
from typing import Any
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domains.platform.logging import correlation_id_ctx, trace_id_ctx
from app.domains.platform.models import AuditLog


class AuditRecord(BaseModel):
    """Immutable record capturing a significant system, strategy, risk, or financial state change."""
    record_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str
    component: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    trace_id: str | None = None


class AuditBuffer:
    """Thread-safe in-memory ring buffer holding recent audit records."""

    def __init__(self, capacity: int = 5000) -> None:
        self._capacity = capacity
        self._buffer: deque[AuditRecord] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, record: AuditRecord) -> None:
        with self._lock:
            self._buffer.append(record)

    def query(
        self,
        actor: str | None = None,
        component: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        with self._lock:
            records = list(self._buffer)

        results = []
        for rec in reversed(records):
            if actor and rec.actor.lower() != actor.lower():
                continue
            if component and rec.component.lower() != component.lower():
                continue
            if action and rec.action.lower() != action.lower():
                continue
            if entity_type and rec.entity_type != entity_type:
                continue
            if entity_id and rec.entity_id != entity_id:
                continue
            if correlation_id and rec.correlation_id != correlation_id:
                continue
            if trace_id and rec.trace_id != trace_id:
                continue
            results.append(rec)
            if len(results) >= limit:
                break
        return results

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buffer)


global_audit_buffer = AuditBuffer(capacity=5000)


class AuditTrailService:
    """Enterprise audit trail service ensuring immutable logging of all critical trading decisions and state transitions."""

    def __init__(self, buffer: AuditBuffer = global_audit_buffer) -> None:
        self._buffer = buffer

    def record(
        self,
        actor: str,
        component: str,
        action: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        db: Session | None = None,
    ) -> AuditRecord:
        """Records an immutable audit event to both in-memory buffer and persistence store."""
        corr_id = correlation_id_ctx.get()
        tr_id = trace_id_ctx.get()

        record = AuditRecord(
            actor=actor,
            component=component,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before_state=before_state,
            after_state=after_state,
            metadata=metadata or {},
            correlation_id=corr_id,
            trace_id=tr_id,
        )

        # 1. In-memory buffer append
        self._buffer.append(record)

        # 2. Database append-only persistence if DB session provided
        if db is not None:
            db_entry = AuditLog(
                id=record.record_id,
                action=f"{component}:{action}",
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                payload=record.model_dump(mode="json"),
            )
            db.add(db_entry)

        return record

    def get_history(
        self,
        actor: str | None = None,
        component: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        db: Session | None = None,
    ) -> list[AuditRecord]:
        """Retrieves audit records from in-memory buffer with fallback to DB."""
        mem_records = self._buffer.query(
            actor=actor,
            component=component,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            limit=limit,
        )
        if mem_records:
            return mem_records

        if db is not None:
            query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
            if action:
                query = query.filter(AuditLog.action.contains(action))
            if entity_type:
                query = query.filter(AuditLog.entity_type == entity_type)
            if entity_id:
                query = query.filter(AuditLog.entity_id == entity_id)

            db_rows = query.limit(limit).all()
            db_records = []
            for row in db_rows:
                p = row.payload or {}
                db_records.append(
                    AuditRecord(
                        record_id=row.id,
                        timestamp=p.get("timestamp", row.created_at.isoformat() if row.created_at else ""),
                        actor=p.get("actor", "system"),
                        component=p.get("component", "unknown"),
                        action=p.get("action", row.action),
                        entity_type=row.entity_type,
                        entity_id=row.entity_id,
                        before_state=p.get("before_state"),
                        after_state=p.get("after_state"),
                        metadata=p.get("metadata", {}),
                        correlation_id=p.get("correlation_id"),
                        trace_id=p.get("trace_id"),
                    )
                )
            return db_records

        return []
