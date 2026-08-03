"""Timeframe derivation: aggregating a coarse frame from a finer one."""
from datetime import datetime, timedelta

import pytest

from app.domains.market_data.enums import Timeframe
from app.domains.market_data.resampling import (
    ResamplingError,
    can_derive,
    resample,
)
from app.domains.market_data.schemas import OHLCVBar
from app.domains.market_data.sessions import IST


def bar(ts: datetime, o: float, h: float, low: float, c: float, v: int) -> OHLCVBar:
    return OHLCVBar(ts=ts, open=o, high=h, low=low, close=c, volume=v)


def session(day: int, count: int, start_hour: int = 9, start_minute: int = 15) -> list[OHLCVBar]:
    """`count` consecutive hourly bars inside one IST trading day."""
    base = datetime(2026, 1, day, start_hour, start_minute, tzinfo=IST)
    return [
        bar(base + timedelta(hours=i), o=100 + i, h=110 + i, low=90 + i, c=105 + i, v=10)
        for i in range(count)
    ]


def test_four_hourly_bars_fold_into_one() -> None:
    out = resample(session(5, 4), Timeframe.h1, Timeframe.h4, IST)
    assert len(out) == 1
    assert (out[0].open, out[0].close) == (100, 108)
    assert out[0].high == 113
    assert out[0].low == 90
    assert out[0].volume == 40


def test_bucket_is_left_labelled_with_its_opening_bar() -> None:
    bars = session(5, 4)
    out = resample(bars, Timeframe.h1, Timeframe.h4, IST)
    assert out[0].ts == bars[0].ts


def test_buckets_never_span_a_session_boundary() -> None:
    """A 6h15m session leaves a short tail under a 4h frame.

    That tail must be emitted as its own bar rather than absorbing the next
    morning's opening hours, which would fabricate an overnight candle.
    """
    bars = session(5, 6) + session(6, 6)
    out = resample(bars, Timeframe.h1, Timeframe.h4, IST)
    days = [b.ts.astimezone(IST).date() for b in out]
    assert days == sorted(days)
    assert len(out) == 4, "two full buckets and two session tails"
    for produced in out:
        assert produced.volume in (20, 40)


def test_day_change_immediately_after_a_full_bucket_does_not_crash() -> None:
    """Regression: the day-boundary flush used to fold an already-emptied bucket."""
    bars = session(5, 4) + session(6, 4)
    out = resample(bars, Timeframe.h1, Timeframe.h4, IST)
    assert len(out) == 2
    assert all(b.volume == 40 for b in out)


def test_empty_input_yields_nothing() -> None:
    assert resample([], Timeframe.h1, Timeframe.h4, IST) == []


def test_non_multiple_derivation_is_refused() -> None:
    # A month is not a whole number of weeks, so the aggregation has no exact form.
    with pytest.raises(ResamplingError, match="whole multiple"):
        resample(session(5, 4), Timeframe.w1, Timeframe.mo1, IST)


@pytest.mark.parametrize(
    ("target", "source", "expected"),
    [
        (Timeframe.h4, Timeframe.h1, True),
        (Timeframe.h1, Timeframe.m15, True),
        # Session anchoring flushes each bucket at the day boundary, so a daily
        # bar aggregates correctly even though a session is shorter than 24h.
        (Timeframe.d1, Timeframe.h1, True),
        (Timeframe.h1, Timeframe.h4, False),   # cannot refine a coarse frame
        (Timeframe.h1, Timeframe.h1, False),   # not an aggregation
        (Timeframe.mo1, Timeframe.w1, False),  # not a whole multiple
    ],
)
def test_derivability(target: Timeframe, source: Timeframe, expected: bool) -> None:
    assert can_derive(target, source) is expected


def test_daily_derived_from_hourly_yields_one_bar_per_session() -> None:
    out = resample(session(5, 6) + session(6, 6), Timeframe.h1, Timeframe.d1, IST)
    assert len(out) == 2
    assert [b.ts.astimezone(IST).day for b in out] == [5, 6]
    assert all(b.volume == 60 for b in out)
