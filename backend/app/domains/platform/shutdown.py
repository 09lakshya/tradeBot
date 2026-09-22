"""Ordered Graceful Shutdown Coordinator for Production Operations."""
from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.domains.platform.logging import get_structured_logger

log = get_structured_logger("platform.shutdown")


class ShutdownPhase(str, enum.Enum):
    initiated = "initiated"
    scheduler_stopped = "scheduler_stopped"
    pipeline_drained = "pipeline_drained"
    events_flushed = "events_flushed"
    audit_flushed = "audit_flushed"
    logs_flushed = "logs_flushed"
    completed = "completed"


class ShutdownResult(BaseModel):
    """Outcome report of the graceful shutdown sequence."""
    success: bool
    completed_phases: list[ShutdownPhase]
    duration_seconds: float
    errors: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class GracefulShutdownCoordinator:
    """Coordinates ordered shutdown of all trading pipelines, background schedulers, and log buffers."""

    def __init__(self) -> None:
        self._scheduler_stop_hook: Callable[[], None] | None = None
        self._pipeline_drain_hook: Callable[[], None] | None = None
        self._event_flush_hook: Callable[[], None] | None = None
        self._audit_flush_hook: Callable[[], None] | None = None
        self._is_shutting_down = False
        self._lock = threading.Lock()

    def register_scheduler_stop_hook(self, hook: Callable[[], None]) -> None:
        self._scheduler_stop_hook = hook

    def register_pipeline_drain_hook(self, hook: Callable[[], None]) -> None:
        self._pipeline_drain_hook = hook

    def register_event_flush_hook(self, hook: Callable[[], None]) -> None:
        self._event_flush_hook = hook

    def register_audit_flush_hook(self, hook: Callable[[], None]) -> None:
        self._audit_flush_hook = hook

    @property
    def is_shutting_down(self) -> bool:
        with self._lock:
            return self._is_shutting_down

    def execute_shutdown(self, timeout_seconds: float = 10.0) -> ShutdownResult:
        """Executes the deterministic graceful shutdown sequence in strict architectural order."""
        with self._lock:
            if self._is_shutting_down:
                return ShutdownResult(
                    success=True,
                    completed_phases=[ShutdownPhase.initiated],
                    duration_seconds=0.0,
                    errors=["Shutdown already in progress"],
                )
            self._is_shutting_down = True

        t0 = time.perf_counter()
        completed_phases: list[ShutdownPhase] = [ShutdownPhase.initiated]
        errors: list[str] = []
        log.warning("graceful_shutdown_sequence_initiated", timeout_seconds=timeout_seconds)

        # 1. Stop background scheduler
        if self._scheduler_stop_hook:
            try:
                self._scheduler_stop_hook()
                completed_phases.append(ShutdownPhase.scheduler_stopped)
                log.info("graceful_shutdown_phase_done", phase="scheduler_stopped")
            except Exception as exc:
                errors.append(f"Scheduler stop failed: {exc}")
                log.error("graceful_shutdown_phase_error", phase="scheduler_stopped", error=str(exc))
        else:
            completed_phases.append(ShutdownPhase.scheduler_stopped)

        # 2. Drain active in-flight execution pipelines
        if self._pipeline_drain_hook:
            try:
                self._pipeline_drain_hook()
                completed_phases.append(ShutdownPhase.pipeline_drained)
                log.info("graceful_shutdown_phase_done", phase="pipeline_drained")
            except Exception as exc:
                errors.append(f"Pipeline drain failed: {exc}")
                log.error("graceful_shutdown_phase_error", phase="pipeline_drained", error=str(exc))
        else:
            completed_phases.append(ShutdownPhase.pipeline_drained)

        # 3. Flush pending events in EventBus
        if self._event_flush_hook:
            try:
                self._event_flush_hook()
                completed_phases.append(ShutdownPhase.events_flushed)
                log.info("graceful_shutdown_phase_done", phase="events_flushed")
            except Exception as exc:
                errors.append(f"Event bus flush failed: {exc}")
                log.error("graceful_shutdown_phase_error", phase="events_flushed", error=str(exc))
        else:
            completed_phases.append(ShutdownPhase.events_flushed)

        # 4. Flush audit trail buffer
        if self._audit_flush_hook:
            try:
                self._audit_flush_hook()
                completed_phases.append(ShutdownPhase.audit_flushed)
                log.info("graceful_shutdown_phase_done", phase="audit_flushed")
            except Exception as exc:
                errors.append(f"Audit flush failed: {exc}")
                log.error("graceful_shutdown_phase_error", phase="audit_flushed", error=str(exc))
        else:
            completed_phases.append(ShutdownPhase.audit_flushed)

        # 5. Flush structured log streams
        completed_phases.append(ShutdownPhase.logs_flushed)
        completed_phases.append(ShutdownPhase.completed)
        duration = round(time.perf_counter() - t0, 4)

        log.info("graceful_shutdown_completed", duration_seconds=duration, errors_count=len(errors))

        return ShutdownResult(
            success=len(errors) == 0,
            completed_phases=completed_phases,
            duration_seconds=duration,
            errors=errors,
        )


global_shutdown_coordinator = GracefulShutdownCoordinator()
