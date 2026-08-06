"""Unit tests for Autonomous Trading Scheduler & Market Operator."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from app.domains.operations.autonomous_scheduler import AutonomousScheduler
from app.domains.operations.models import OperationalMode
from app.domains.operations.schemas import SchedulerConfigSchema


@pytest.mark.asyncio
async def test_scheduler_modes_and_controls():
    scheduler = AutonomousScheduler()
    status = scheduler.get_status()
    assert status.mode == OperationalMode.autonomous

    scheduler.pause()
    assert scheduler.get_status().mode == OperationalMode.paused

    scheduler.resume()
    assert scheduler.get_status().mode == OperationalMode.autonomous

    scheduler.stop()
    assert scheduler.get_status().mode == OperationalMode.stopped


@pytest.mark.asyncio
async def test_scheduler_execution_cycle():
    executed_flag = False

    def callback():
        nonlocal executed_flag
        executed_flag = True

    scheduler = AutonomousScheduler()
    scheduler.set_execution_callback(callback)
    scheduler.set_mode(OperationalMode.manual_override, manual_override=True)

    result = await scheduler.execute_single_cycle()
    assert result["executed"] is True
    assert executed_flag is True
    assert result["duration_ms"] >= 0.0


def test_scheduler_market_hours_evaluation():
    scheduler = AutonomousScheduler()
    # Wednesday 05:00 UTC (10:30 AM IST - NSE Market open)
    open_dt = datetime(2026, 8, 5, 5, 0, 0, tzinfo=timezone.utc)
    assert scheduler.is_market_open(open_dt) is True
    assert scheduler.is_weekend(open_dt) is False

    # Saturday 14:00 UTC (Weekend closed)
    sat_dt = datetime(2026, 8, 8, 14, 0, 0, tzinfo=timezone.utc)
    assert scheduler.is_market_open(sat_dt) is False
    assert scheduler.is_weekend(sat_dt) is True
