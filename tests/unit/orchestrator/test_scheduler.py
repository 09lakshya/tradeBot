"""Unit tests for the Execution Scheduler."""
from datetime import datetime, timezone
import pytest

from app.domains.orchestrator.exceptions import SchedulerError
from app.domains.orchestrator.scheduler import ExecutionScheduler
from app.domains.trading.clock import FixedClock


def test_scheduler_manual_trigger():
    clock = FixedClock(datetime(2025, 4, 15, 10, 0, 0, tzinfo=timezone.utc))
    scheduler = ExecutionScheduler(interval_seconds=60.0, clock=clock)

    run_count = 0

    def job():
        nonlocal run_count
        run_count += 1
        return "ok"

    scheduler.start(job)
    # Trigger synchronously
    res = scheduler.trigger_now()
    assert res == "ok"
    assert run_count == 1
    assert scheduler.total_runs == 1
    assert scheduler.last_run_timestamp == clock.now()

    scheduler.stop()
    assert not scheduler.is_running


def test_scheduler_interval_validation():
    scheduler = ExecutionScheduler()
    with pytest.raises(SchedulerError):
        scheduler.set_interval(-10.0)

    scheduler.set_interval(30.0)
    assert scheduler.interval_seconds == 30.0
