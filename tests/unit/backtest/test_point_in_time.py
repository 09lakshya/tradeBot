"""Unit tests for PointInTimeDataFeed and look-ahead bias prevention."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.backtest.exceptions import LookAheadBiasError
from app.domains.trading.clock import ReplayClock


def test_point_in_time_data_feed_lookahead_prevention():
    inst_id = uuid.uuid4()
    t1 = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    t2 = datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc)
    t3 = datetime(2025, 1, 3, 9, 15, tzinfo=timezone.utc)

    bars = [
        HistoricalBar(inst_id, "TCS", t1, Decimal("3500.0"), Decimal("3550.0"), Decimal("3490.0"), Decimal("3540.0"), 10000),
        HistoricalBar(inst_id, "TCS", t2, Decimal("3540.0"), Decimal("3600.0"), Decimal("3530.0"), Decimal("3580.0"), 15000),
        HistoricalBar(inst_id, "TCS", t3, Decimal("3580.0"), Decimal("3620.0"), Decimal("3570.0"), Decimal("3610.0"), 20000),
    ]

    clock = ReplayClock(start_time=t1)
    feed = PointInTimeDataFeed(clock=clock, bars=bars)

    # At t1, only t1 bar should be visible
    latest = feed.get_latest_bar(inst_id)
    assert latest is not None
    assert latest.timestamp == t1
    assert latest.close == Decimal("3540.0")

    history = feed.get_history(inst_id, lookback_bars=10)
    assert len(history) == 1
    assert history[0].timestamp == t1

    # Asserting no lookahead at t1 passes
    feed.assert_no_lookahead(t1)

    # Asserting no lookahead for future bar t2 raises LookAheadBiasError!
    with pytest.raises(LookAheadBiasError) as exc_info:
        feed.assert_no_lookahead(t2, instrument_id=inst_id)
    assert "Look-Ahead Bias Violation" in str(exc_info.value)

    # Advance clock to t2
    clock.step_to(t2)
    latest = feed.get_latest_bar(inst_id)
    assert latest.timestamp == t2
    history = feed.get_history(inst_id, lookback_bars=10)
    assert len(history) == 2

    # Advance clock to t3
    clock.step_to(t3)
    latest = feed.get_latest_bar(inst_id)
    assert latest.timestamp == t3
    history = feed.get_history(inst_id, lookback_bars=10)
    assert len(history) == 3
