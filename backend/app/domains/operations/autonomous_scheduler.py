"""Autonomous Trading Scheduler & Market Operator for Phase 10."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

from app.domains.market_data.calendar import MarketCalendar
from app.domains.operations.models import OperationalMode
from app.domains.operations.schemas import SchedulerConfigSchema, SchedulerStatusResponse
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.scheduler")

# Standard US NYSE / Nasdaq market hours in UTC (9:30 AM ET = 13:30/14:30 UTC, 4:00 PM ET = 20:00/21:00 UTC)
# For flexible paper trading simulation, configurable default opening: 09:30 - 16:00 ET.
DEFAULT_STATE_FILE = Path("scratch/autonomous_scheduler_state.json")


class AutonomousScheduler:
    """Institutional autonomous market operator with calendar awareness, pause/resume, and crash recovery."""

    def __init__(
        self,
        calendar: MarketCalendar | None = None,
        state_file: Path = DEFAULT_STATE_FILE,
    ) -> None:
        self.calendar = calendar or MarketCalendar()
        self.state_file = state_file
        self.config = SchedulerConfigSchema()
        self._mode = OperationalMode.autonomous
        self._is_running = False
        self._execution_count = 0
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._callback: Callable[[], Any] | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._last_run_timestamp: str | None = None
        self._next_run_timestamp: str | None = None

        # Attempt crash recovery
        self._restore_state()

    def set_execution_callback(self, callback: Callable[[], Any]) -> None:
        """Sets the callback function to execute on each scheduler cycle."""
        with self._lock:
            self._callback = callback

    def configure(self, config: SchedulerConfigSchema) -> SchedulerConfigSchema:
        with self._lock:
            self.config = config
            self._mode = config.mode
            self._persist_state()
            logger.info("scheduler_configured", mode=self._mode.value, interval=config.interval_seconds)
            return self.config

    def set_mode(self, mode: OperationalMode, manual_override: bool = False) -> None:
        with self._lock:
            self._mode = mode
            if manual_override:
                self.config.mode = OperationalMode.manual_override
            else:
                self.config.mode = mode
            self._persist_state()
            logger.info("scheduler_mode_changed", new_mode=mode.value, manual_override=manual_override)

    def is_market_open(self, dt: datetime | None = None) -> bool:
        """Evaluates whether current time falls within valid Indian market (NSE/BSE) trading hours (9:15 AM to 3:30 PM IST / 03:45 to 10:00 UTC)."""
        if dt is None:
            dt = datetime.now(UTC)

        # Check weekend (Saturday / Sunday)
        if dt.weekday() in (5, 6):
            return False

        # Check calendar holiday if configured
        if hasattr(self.calendar, "is_holiday") and self.calendar.is_holiday(dt.date()):
            return False

        # Check standard NSE/BSE trading window (9:15 AM to 3:30 PM IST -> 03:45 to 10:00 UTC)
        utc_time = dt.time()
        start_time = dtime(3, 45)
        end_time = dtime(10, 0)
        return start_time <= utc_time <= end_time

    def is_weekend(self, dt: datetime | None = None) -> bool:
        if dt is None:
            dt = datetime.now(UTC)
        return dt.weekday() in (5, 6)

    def is_holiday(self, dt: datetime | None = None) -> bool:
        if dt is None:
            dt = datetime.now(UTC)
        if hasattr(self.calendar, "is_holiday"):
            return self.calendar.is_holiday(dt.date())
        return False

    def should_execute_now(self, dt: datetime | None = None) -> tuple[bool, str]:
        """Evaluates all operational conditions to determine whether cycle should execute."""
        if dt is None:
            dt = datetime.now(UTC)

        if self._mode == OperationalMode.stopped:
            return False, "Scheduler is in STOPPED mode"

        if self._mode == OperationalMode.paused:
            return False, "Scheduler is in PAUSED mode"

        if self._mode == OperationalMode.manual_override:
            return True, "Manual Override enabled"

        # Autonomous mode checks
        if self.config.respect_weekends and self.is_weekend(dt):
            return False, "Market closed (Weekend)"

        if self.config.respect_holidays and self.is_holiday(dt):
            return False, "Market closed (Holiday)"

        if self.config.auto_start_pre_market or self.config.auto_stop_post_market:
            # Under paper trading, execution is active during market hours or configured window
            market_open = self.is_market_open(dt)
            if not market_open:
                return False, "Outside standard market operating hours"

        return True, "Autonomous market operating window active"

    async def execute_single_cycle(self) -> dict[str, Any]:
        """Executes a single cycle synchronously or asynchronously."""
        start_t = time.perf_counter()
        now_iso = datetime.now(UTC).isoformat()
        should_run, reason = self.should_execute_now()

        entry = {
            "cycle": self._execution_count + 1,
            "timestamp": now_iso,
            "mode": self._mode.value,
            "executed": False,
            "reason": reason,
            "duration_ms": 0.0,
            "error": None,
        }

        if not should_run:
            logger.info("scheduler_cycle_skipped", reason=reason, mode=self._mode.value)
            return entry

        try:
            with self._lock:
                callback = self._callback

            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()

            self._execution_count += 1
            duration = round((time.perf_counter() - start_t) * 1000.0, 2)
            entry["executed"] = True
            entry["duration_ms"] = duration
            self._last_run_timestamp = now_iso

            logger.info("scheduler_cycle_completed", cycle=self._execution_count, duration_ms=duration)
        except Exception as exc:
            duration = round((time.perf_counter() - start_t) * 1000.0, 2)
            entry["error"] = str(exc)
            entry["duration_ms"] = duration
            logger.error("scheduler_cycle_error", error=str(exc))

        with self._lock:
            self._history.append(entry)
            if len(self._history) > 100:
                self._history = self._history[-100:]
            self._persist_state()

        return entry

    def start(self) -> None:
        """Starts background loop if not running."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            if self._mode == OperationalMode.stopped:
                self._mode = OperationalMode.autonomous
            self._persist_state()

    def stop(self) -> None:
        """Stops background scheduler."""
        with self._lock:
            self._is_running = False
            self._mode = OperationalMode.stopped
            self._persist_state()
            logger.info("scheduler_stopped")

    def pause(self) -> None:
        with self._lock:
            self._mode = OperationalMode.paused
            self._persist_state()
            logger.info("scheduler_paused")

    def resume(self) -> None:
        with self._lock:
            self._mode = OperationalMode.autonomous
            self._is_running = True
            self._persist_state()
            logger.info("scheduler_resumed")

    def get_status(self) -> SchedulerStatusResponse:
        with self._lock:
            dt = datetime.now(UTC)
            return SchedulerStatusResponse(
                mode=self._mode,
                is_running=self._is_running,
                is_market_open=self.is_market_open(dt),
                is_weekend=self.is_weekend(dt),
                is_holiday=self.is_holiday(dt),
                interval_seconds=self.config.interval_seconds,
                last_run_timestamp=self._last_run_timestamp,
                next_run_timestamp=self._next_run_timestamp,
                total_execution_cycles=self._execution_count,
                recent_execution_history=list(self._history[-10:]),
            )

    def _persist_state(self) -> None:
        """Persists state to disk for crash recovery."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "mode": self._mode.value,
                "is_running": self._is_running,
                "execution_count": self._execution_count,
                "config": self.config.model_dump(),
                "last_run_timestamp": self._last_run_timestamp,
                "history": self._history[-20:],
            }
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("scheduler_persist_state_failed", error=str(exc))

    def _restore_state(self) -> None:
        """Restores state from disk following restart or crash."""
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._mode = OperationalMode(data.get("mode", OperationalMode.autonomous.value))
            self._is_running = data.get("is_running", False)
            self._execution_count = data.get("execution_count", 0)
            self._last_run_timestamp = data.get("last_run_timestamp")
            self._history = data.get("history", [])
            if "config" in data:
                self.config = SchedulerConfigSchema(**data["config"])
            logger.info("scheduler_state_restored", mode=self._mode.value, cycles=self._execution_count)
        except Exception as exc:
            logger.warning("scheduler_restore_state_failed", error=str(exc))
