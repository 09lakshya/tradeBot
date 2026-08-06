"""Centralized Structured Logging Framework with Context Propagation and In-Memory Buffer."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
import threading
import traceback
from typing import Any, Iterator
from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# Context Variables for Asynchronous Context Propagation
# -------------------------------------------------------------------------
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id_ctx", default=None)
cycle_id_ctx: ContextVar[str | None] = ContextVar("cycle_id_ctx", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id_ctx", default=None)
span_id_ctx: ContextVar[str | None] = ContextVar("span_id_ctx", default=None)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)
order_id_ctx: ContextVar[str | None] = ContextVar("order_id_ctx", default=None)
strategy_id_ctx: ContextVar[str | None] = ContextVar("strategy_id_ctx", default=None)
symbol_ctx: ContextVar[str | None] = ContextVar("symbol_ctx", default=None)
stage_ctx: ContextVar[str | None] = ContextVar("stage_ctx", default=None)


@contextmanager
def log_context(
    *,
    correlation_id: str | None = None,
    cycle_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    request_id: str | None = None,
    order_id: str | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    stage: str | None = None,
) -> Iterator[None]:
    """Context manager to bind context variables for logging and tracing in the current async task/thread."""
    tokens = []
    if correlation_id is not None:
        tokens.append((correlation_id_ctx, correlation_id_ctx.set(correlation_id)))
    if cycle_id is not None:
        tokens.append((cycle_id_ctx, cycle_id_ctx.set(cycle_id)))
    if trace_id is not None:
        tokens.append((trace_id_ctx, trace_id_ctx.set(trace_id)))
    if span_id is not None:
        tokens.append((span_id_ctx, span_id_ctx.set(span_id)))
    if request_id is not None:
        tokens.append((request_id_ctx, request_id_ctx.set(request_id)))
    if order_id is not None:
        tokens.append((order_id_ctx, order_id_ctx.set(order_id)))
    if strategy_id is not None:
        tokens.append((strategy_id_ctx, strategy_id_ctx.set(strategy_id)))
    if symbol is not None:
        tokens.append((symbol_ctx, symbol_ctx.set(symbol)))
    if stage is not None:
        tokens.append((stage_ctx, stage_ctx.set(stage)))

    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


# -------------------------------------------------------------------------
# Log Entry Schema
# -------------------------------------------------------------------------
class StructuredLogEntry(BaseModel):
    """Immutable model representing a structured JSON log entry."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str
    logger: str
    message: str
    correlation_id: str | None = None
    cycle_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    order_id: str | None = None
    strategy_id: str | None = None
    symbol: str | None = None
    stage: str | None = None
    latency_ms: float | None = None
    exception: dict[str, Any] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------------------
# In-Memory Circular Log Buffer
# -------------------------------------------------------------------------
class LogBuffer:
    """Thread-safe circular log buffer for live log queries via monitoring endpoints."""

    def __init__(self, capacity: int = 2000) -> None:
        self._capacity = capacity
        self._buffer: deque[StructuredLogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, entry: StructuredLogEntry) -> None:
        with self._lock:
            self._buffer.append(entry)

    def get_entries(
        self,
        level: str | None = None,
        correlation_id: str | None = None,
        cycle_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[StructuredLogEntry]:
        with self._lock:
            entries = list(self._buffer)

        # Apply filtering
        filtered = []
        for entry in reversed(entries):
            if level and entry.level.upper() != level.upper():
                continue
            if correlation_id and entry.correlation_id != correlation_id:
                continue
            if cycle_id and entry.cycle_id != cycle_id:
                continue
            if trace_id and entry.trace_id != trace_id:
                continue
            filtered.append(entry)
            if len(filtered) >= limit:
                break

        return filtered

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)


# Global singleton buffer
global_log_buffer = LogBuffer(capacity=2000)


# -------------------------------------------------------------------------
# Structured Logger Implementation
# -------------------------------------------------------------------------
class StructuredLogger:
    """Production-grade structured logger emitting JSON and capturing runtime context."""

    def __init__(self, name: str, bound_context: dict[str, Any] | None = None) -> None:
        self.name = name
        self._bound_context: dict[str, Any] = bound_context or {}
        self._std_logger = logging.getLogger(name)

    def bind(self, **kwargs: Any) -> StructuredLogger:
        """Returns a child logger with bound contextual attributes."""
        merged = {**self._bound_context, **kwargs}
        return StructuredLogger(self.name, bound_context=merged)

    def _build_entry(
        self,
        level: str,
        msg: str,
        exc_info: Any = None,
        latency_ms: float | None = None,
        **kwargs: Any,
    ) -> StructuredLogEntry:
        # Merge contextvars and bound context and direct kwargs
        corr_id = kwargs.pop("correlation_id", correlation_id_ctx.get())
        cyc_id = kwargs.pop("cycle_id", cycle_id_ctx.get())
        tr_id = kwargs.pop("trace_id", trace_id_ctx.get())
        sp_id = kwargs.pop("span_id", span_id_ctx.get())
        req_id = kwargs.pop("request_id", request_id_ctx.get())
        ord_id = kwargs.pop("order_id", order_id_ctx.get())
        strat_id = kwargs.pop("strategy_id", strategy_id_ctx.get())
        sym = kwargs.pop("symbol", symbol_ctx.get())
        stg = kwargs.pop("stage", stage_ctx.get())
        lat = kwargs.pop("latency_ms", latency_ms)

        exc_dict: dict[str, Any] | None = None
        if exc_info:
            if isinstance(exc_info, BaseException):
                exc_dict = {
                    "type": exc_info.__class__.__name__,
                    "message": str(exc_info),
                    "traceback": "".join(traceback.format_tb(exc_info.__traceback__)),
                }
            elif exc_info is True:
                exc_type, exc_val, exc_tb = sys.exc_info()
                if exc_val is not None:
                    exc_dict = {
                        "type": exc_val.__class__.__name__,
                        "message": str(exc_val),
                        "traceback": "".join(traceback.format_tb(exc_tb)),
                    }

        extra_data = {**self._bound_context, **kwargs}

        return StructuredLogEntry(
            level=level,
            logger=self.name,
            message=msg,
            correlation_id=corr_id,
            cycle_id=cyc_id,
            trace_id=tr_id,
            span_id=sp_id,
            request_id=req_id,
            order_id=ord_id,
            strategy_id=strat_id,
            symbol=sym,
            stage=stg,
            latency_ms=lat,
            exception=exc_dict,
            extra=extra_data,
        )

    def _log(
        self,
        level_num: int,
        level_name: str,
        msg: str,
        *args: Any,
        exc_info: Any = None,
        latency_ms: float | None = None,
        **kwargs: Any,
    ) -> None:
        if not self._std_logger.isEnabledFor(level_num):
            return

        formatted_msg = msg % args if args else msg

        entry = self._build_entry(
            level=level_name,
            msg=formatted_msg,
            exc_info=exc_info,
            latency_ms=latency_ms,
            **kwargs,
        )
        global_log_buffer.append(entry)

        json_str = entry.model_dump_json()
        self._std_logger.log(level_num, json_str)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, "DEBUG", msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, "INFO", msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, "WARNING", msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, exc_info: Any = None, **kwargs: Any) -> None:
        self._log(logging.ERROR, "ERROR", msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, *args: Any, exc_info: Any = None, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, "CRITICAL", msg, *args, exc_info=exc_info, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, "ERROR", msg, *args, exc_info=True, **kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """Factory function for retrieving a named StructuredLogger."""
    return StructuredLogger(name)
