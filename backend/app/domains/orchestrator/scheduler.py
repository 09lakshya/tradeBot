"""Configurable scheduling engine for autonomous execution cycles."""
import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from app.domains.orchestrator.exceptions import SchedulerError
from app.domains.trading.clock import Clock, SystemClock

log = logging.getLogger(__name__)


class ExecutionScheduler:
    """Manages scheduled periodic or cron-like triggering of execution cycles."""

    def __init__(
        self,
        interval_seconds: float = 60.0,
        clock: Clock | None = None,
    ):
        self.interval_seconds = interval_seconds
        self.clock = clock or SystemClock()
        self._running = False
        self._task: asyncio.Task | None = None
        self._job: Callable[[], Coroutine[Any, Any, None]] | Callable[[], None] | None = None
        self._total_runs: int = 0
        self._last_run_timestamp: datetime | None = None
        self._last_run_error: str | None = None

    @property
    def is_running(self) -> bool:
        """Returns True if the background scheduler loop is currently active."""
        return self._running

    @property
    def total_runs(self) -> int:
        """Returns the total number of executed cycles."""
        return self._total_runs

    @property
    def last_run_timestamp(self) -> datetime | None:
        """Returns the timestamp of the last executed cycle."""
        return self._last_run_timestamp

    def set_interval(self, seconds: float) -> None:
        """Dynamically updates the schedule interval."""
        if seconds <= 0:
            raise SchedulerError(f"Invalid schedule interval: {seconds}s (must be > 0)")
        self.interval_seconds = seconds

    def start(self, job: Callable[[], Coroutine[Any, Any, None]] | Callable[[], None]) -> None:
        """Starts the background asynchronous scheduler loop."""
        if self._running:
            log.warning("Scheduler is already running.")
            return

        self._job = job
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            # No running event loop in current thread
            pass

    async def _run_loop(self) -> None:
        """Asynchronous execution loop with drift compensation."""
        log.info("Scheduler started with interval: %0.2fs", self.interval_seconds)
        while self._running:
            start_ts = self.clock.now()
            self._last_run_timestamp = start_ts
            self._total_runs += 1

            try:
                if self._job:
                    res = self._job()
                    if asyncio.iscoroutine(res):
                        await res
                self._last_run_error = None
            except Exception as err:
                self._last_run_error = str(err)
                log.error("Error during scheduled cycle run: %s", err, exc_info=True)

            # Drift compensation
            elapsed = (self.clock.now() - start_ts).total_seconds()
            sleep_duration = max(0.01, self.interval_seconds - elapsed)
            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        """Stops the background scheduler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        log.info("Scheduler stopped.")

    def trigger_now(self) -> Any:
        """Manually and synchronously triggers a single cycle."""
        if not self._job:
            raise SchedulerError("No job has been registered with the scheduler.")
        self._last_run_timestamp = self.clock.now()
        self._total_runs += 1
        return self._job()
