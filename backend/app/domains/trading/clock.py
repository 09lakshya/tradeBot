"""Clock abstraction for the Trading domain.

Enforces that no component in the OMS calls `datetime.now()` directly.
Supports real-time execution, unit test time control, and deterministic historical replay.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta


class Clock(ABC):
    """Abstract Clock interface."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current UTC timestamp."""
        raise NotImplementedError


class SystemClock(Clock):
    """Real system wall-clock returning current UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock(Clock):
    """Controllable clock for unit tests and step-by-step simulations."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is None:
            self._current = datetime.now(UTC)
        else:
            self._current = (
                initial_time if initial_time.tzinfo is not None
                else initial_time.replace(tzinfo=UTC)
            )

    def now(self) -> datetime:
        return self._current

    def set_time(self, new_time: datetime) -> None:
        self._current = (
            new_time if new_time.tzinfo is not None
            else new_time.replace(tzinfo=UTC)
        )

    def advance(self, duration: timedelta) -> datetime:
        self._current += duration
        return self._current


class ReplayClock(Clock):
    """Replay clock driven externally by historical market data bars or event logs."""

    def __init__(self, start_time: datetime) -> None:
        self._current = (
            start_time if start_time.tzinfo is not None
            else start_time.replace(tzinfo=UTC)
        )

    def now(self) -> datetime:
        return self._current

    def step_to(self, new_time: datetime) -> None:
        target = (
            new_time if new_time.tzinfo is not None
            else new_time.replace(tzinfo=UTC)
        )
        if target < self._current:
            raise ValueError(f"Replay clock cannot step backwards: {target} < {self._current}")
        self._current = target
