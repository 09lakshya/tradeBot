"""Multi-State Circuit Breaker Subsystem for External Dependency Protection."""
from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.domains.platform.exceptions import CircuitBreakerOpenError
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger("platform.circuit_breaker")
T = TypeVar("T")


class CircuitBreakerState(str, enum.Enum):
    closed = "closed"        # Normal operation: requests pass through
    open = "open"            # Tripped: fail fast without executing call
    half_open = "half_open"  # Testing recovery: allowing limited probe requests


class CircuitBreakerSnapshot(BaseModel):
    """Snapshot representation of a circuit breaker's real-time state."""
    name: str
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    failure_threshold: int
    recovery_timeout_seconds: float
    half_open_success_threshold: int
    total_trips: int
    last_failure_time: str | None = None
    last_state_change: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CircuitBreaker:
    """Thread-safe state machine implementing the Circuit Breaker pattern."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self._state = CircuitBreakerState.closed
        self._failure_count = 0
        self._half_open_success_count = 0
        self._total_trips = 0
        self._last_failure_time: float | None = None
        self._last_state_change = datetime.now(UTC).isoformat()
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            self._evaluate_state_transition()
            return self._state

    def _evaluate_state_transition(self) -> None:
        """Evaluates whether an OPEN circuit breaker has timed out and should transition to HALF_OPEN."""
        if self._state == CircuitBreakerState.open and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout_seconds:
                self._state = CircuitBreakerState.half_open
                self._half_open_success_count = 0
                self._last_state_change = datetime.now(UTC).isoformat()
                log.warning(
                    "circuit_breaker_half_open_probe",
                    breaker=self.name,
                    elapsed_seconds=elapsed,
                    recovery_timeout=self.recovery_timeout_seconds,
                )

    def record_success(self) -> None:
        """Records a successful call."""
        with self._lock:
            if self._state == CircuitBreakerState.half_open:
                self._half_open_success_count += 1
                if self._half_open_success_count >= self.half_open_success_threshold:
                    self._state = CircuitBreakerState.closed
                    self._failure_count = 0
                    self._half_open_success_count = 0
                    self._last_state_change = datetime.now(UTC).isoformat()
                    log.info("circuit_breaker_recovered", breaker=self.name, state="closed")
            elif self._state == CircuitBreakerState.closed:
                self._failure_count = 0

    def record_failure(self, exc: Exception) -> None:
        """Records a failed call and trips circuit if threshold exceeded."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitBreakerState.half_open:
                # Any failure during half-open immediately trips back to OPEN
                self._state = CircuitBreakerState.open
                self._total_trips += 1
                self._last_state_change = datetime.now(UTC).isoformat()
                log.error(
                    "circuit_breaker_half_open_failed",
                    breaker=self.name,
                    error=str(exc),
                    total_trips=self._total_trips,
                )
            elif self._state == CircuitBreakerState.closed and self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.open
                self._total_trips += 1
                self._last_state_change = datetime.now(UTC).isoformat()
                log.error(
                    "circuit_breaker_tripped_open",
                    breaker=self.name,
                    failure_count=self._failure_count,
                    threshold=self.failure_threshold,
                    error=str(exc),
                    total_trips=self._total_trips,
                )

    def trip(self, reason: str = "Manually tripped") -> None:
        """Manually forces the circuit breaker into OPEN state."""
        with self._lock:
            self._state = CircuitBreakerState.open
            self._failure_count = self.failure_threshold
            self._total_trips += 1
            self._last_failure_time = time.time()
            self._last_state_change = datetime.now(UTC).isoformat()
            log.warning("circuit_breaker_manually_tripped", breaker=self.name, reason=reason)

    def reset(self) -> None:
        """Manually forces the circuit breaker back to CLOSED state."""
        with self._lock:
            self._state = CircuitBreakerState.closed
            self._failure_count = 0
            self._half_open_success_count = 0
            self._last_state_change = datetime.now(UTC).isoformat()
            log.info("circuit_breaker_manually_reset", breaker=self.name)

    @contextmanager
    def protect(self) -> Iterator[None]:
        """Context manager protecting a code block with the circuit breaker."""
        with self._lock:
            self._evaluate_state_transition()
            if self._state == CircuitBreakerState.open:
                remaining = self.recovery_timeout_seconds - (
                    time.time() - (self._last_failure_time or time.time())
                )
                raise CircuitBreakerOpenError(self.name, max(0.0, remaining))

        try:
            yield
            self.record_success()
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            self.record_failure(exc)
            raise

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Executes a callable under circuit breaker protection."""
        with self.protect():
            return fn(*args, **kwargs)

    def get_snapshot(self) -> CircuitBreakerSnapshot:
        with self._lock:
            self._evaluate_state_transition()
            return CircuitBreakerSnapshot(
                name=self.name,
                state=self._state,
                failure_count=self._failure_count,
                success_count=self._half_open_success_count,
                failure_threshold=self.failure_threshold,
                recovery_timeout_seconds=self.recovery_timeout_seconds,
                half_open_success_threshold=self.half_open_success_threshold,
                total_trips=self._total_trips,
                last_failure_time=(
                    datetime.fromtimestamp(self._last_failure_time, tz=UTC).isoformat()
                    if self._last_failure_time
                    else None
                ),
                last_state_change=self._last_state_change,
            )


class CircuitBreakerRegistry:
    """Central registry of named circuit breakers across the platform."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    recovery_timeout_seconds=recovery_timeout_seconds,
                    half_open_success_threshold=half_open_success_threshold,
                )
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        with self._lock:
            return self._breakers.get(name)

    def list_all(self) -> list[CircuitBreakerSnapshot]:
        with self._lock:
            return [b.get_snapshot() for b in self._breakers.values()]

    def reset_all(self) -> None:
        with self._lock:
            for b in self._breakers.values():
                b.reset()


global_circuit_breaker_registry = CircuitBreakerRegistry()
