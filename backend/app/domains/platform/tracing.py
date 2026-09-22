"""Distributed Tracing and Execution Span Management for Production Observability."""
from __future__ import annotations

import enum
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.domains.platform.logging import (
    log_context,
    span_id_ctx,
    trace_id_ctx,
)

F = TypeVar("F", bound=Callable[..., Any])


class SpanStatus(str, enum.Enum):
    ok = "ok"
    error = "error"
    unset = "unset"


class SpanKind(str, enum.Enum):
    internal = "internal"
    pipeline_stage = "pipeline_stage"
    server = "server"
    client = "client"


class SpanRecord(BaseModel):
    """Immutable record of an individual execution span within a trace."""
    trace_id: uuid.UUID
    span_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_id: uuid.UUID | None = None
    name: str
    kind: SpanKind = SpanKind.internal
    status: SpanStatus = SpanStatus.unset
    start_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str | None = None
    duration_ms: float | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None


class TraceRecord(BaseModel):
    """Consolidated representation of a distributed execution trace containing its complete span tree."""
    trace_id: uuid.UUID
    root_span_id: uuid.UUID
    name: str
    start_time: str
    end_time: str | None = None
    duration_ms: float | None = None
    status: SpanStatus = SpanStatus.unset
    spans: list[SpanRecord] = Field(default_factory=list)
    tags: dict[str, Any] = Field(default_factory=dict)


class TraceCollector:
    """Thread-safe ring buffer storing recent execution traces for real-time telemetry and debugging."""

    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._traces: deque[TraceRecord] = deque(maxlen=capacity)
        self._active_spans: dict[uuid.UUID, list[SpanRecord]] = {}
        self._lock = threading.Lock()

    def record_span(self, span: SpanRecord) -> None:
        with self._lock:
            if span.trace_id not in self._active_spans:
                self._active_spans[span.trace_id] = []
            self._active_spans[span.trace_id].append(span)

    def finalize_trace(
        self,
        trace_id: uuid.UUID,
        root_span: SpanRecord,
        tags: dict[str, Any] | None = None,
    ) -> TraceRecord:
        with self._lock:
            spans = self._active_spans.pop(trace_id, [root_span])
            # Ensure root span is in list
            if not any(s.span_id == root_span.span_id for s in spans):
                spans.insert(0, root_span)

            trace = TraceRecord(
                trace_id=trace_id,
                root_span_id=root_span.span_id,
                name=root_span.name,
                start_time=root_span.start_time,
                end_time=root_span.end_time,
                duration_ms=root_span.duration_ms,
                status=root_span.status,
                spans=spans,
                tags=tags or root_span.tags,
            )
            self._traces.append(trace)
            return trace

    def get_traces(
        self,
        trace_id: uuid.UUID | None = None,
        name: str | None = None,
        status: SpanStatus | None = None,
        limit: int = 50,
    ) -> list[TraceRecord]:
        with self._lock:
            traces = list(self._traces)

        results = []
        for tr in reversed(traces):
            if trace_id and tr.trace_id != trace_id:
                continue
            if name and name.lower() not in tr.name.lower():
                continue
            if status and tr.status != status:
                continue
            results.append(tr)
            if len(results) >= limit:
                break
        return results

    def get_trace_by_id(self, trace_id: uuid.UUID) -> TraceRecord | None:
        with self._lock:
            for tr in self._traces:
                if tr.trace_id == trace_id:
                    return tr
        return None

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()
            self._active_spans.clear()


global_trace_collector = TraceCollector(capacity=1000)


class ActiveSpan:
    """Active span handle facilitating tag additions, event logging, and error tracking."""

    def __init__(self, record: SpanRecord) -> None:
        self.record = record

    def set_tag(self, key: str, value: Any) -> None:
        self.record.tags[key] = value

    def log_event(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.record.events.append({
            "name": name,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload or {},
        })

    def set_error(self, err: Exception | str) -> None:
        self.record.status = SpanStatus.error
        self.record.error_message = str(err)


@contextmanager
def trace_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.internal,
    tags: dict[str, Any] | None = None,
    trace_id: uuid.UUID | None = None,
    collector: TraceCollector = global_trace_collector,
) -> Iterator[ActiveSpan]:
    """Context manager creating a child span and propagating trace/span context variables."""
    curr_trace_str = trace_id_ctx.get()
    curr_span_str = span_id_ctx.get()

    if trace_id is not None:
        effective_trace_id = trace_id
        parent_span_id = None
        is_root = True
    elif curr_trace_str is not None:
        effective_trace_id = uuid.UUID(curr_trace_str)
        parent_span_id = uuid.UUID(curr_span_str) if curr_span_str else None
        is_root = False
    else:
        effective_trace_id = uuid.uuid4()
        parent_span_id = None
        is_root = True

    span_id = uuid.uuid4()
    span_record = SpanRecord(
        trace_id=effective_trace_id,
        span_id=span_id,
        parent_id=parent_span_id,
        name=name,
        kind=kind,
        tags=tags or {},
    )
    active = ActiveSpan(span_record)
    t_start = time.perf_counter()

    with log_context(trace_id=str(effective_trace_id), span_id=str(span_id)):
        try:
            yield active
            if span_record.status == SpanStatus.unset:
                span_record.status = SpanStatus.ok
        except Exception as exc:
            span_record.status = SpanStatus.error
            span_record.error_message = str(exc)
            raise
        finally:
            t_end = time.perf_counter()
            span_record.end_time = datetime.now(UTC).isoformat()
            span_record.duration_ms = round((t_end - t_start) * 1000.0, 4)

            collector.record_span(span_record)
            if is_root:
                collector.finalize_trace(effective_trace_id, span_record)


def traced(
    name: str | None = None,
    kind: SpanKind = SpanKind.internal,
    tags: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace a synchronous or asynchronous callable."""
    def decorator(fn: F) -> F:
        span_name = name or fn.__name__

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, kind=kind, tags=tags):
                return fn(*args, **kwargs)

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, kind=kind, tags=tags):
                return await fn(*args, **kwargs)

        import inspect
        if inspect.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
