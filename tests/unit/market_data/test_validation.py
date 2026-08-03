"""Data quality validation — nothing corrupt may pass through."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.market_data.enums import QuarantineReason, Timeframe
from app.domains.market_data.schemas import OHLCVBar
from app.domains.market_data.sessions import IST
from app.domains.market_data.validation import DataQualityValidator


def bar(ts: datetime, o: float = 100, h: float = 105, low: float = 95,
        c: float = 102, v: int = 1000) -> OHLCVBar:
    return OHLCVBar(ts=ts, open=o, high=h, low=low, close=c, volume=v)


BASE = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


def test_clean_bars_pass() -> None:
    bars = [bar(BASE + timedelta(days=i)) for i in range(3)]
    result = DataQualityValidator().validate(bars, Timeframe.d1)
    assert len(result.valid) == 3
    assert result.rejected_count == 0


def test_duplicate_candles_quarantined() -> None:
    bars = [bar(BASE), bar(BASE)]
    result = DataQualityValidator().validate(bars, Timeframe.d1)
    assert len(result.valid) == 1
    assert result.quarantined[0].reason is QuarantineReason.duplicate


def test_negative_price_quarantined() -> None:
    result = DataQualityValidator().validate(
        [bar(BASE, o=-1, h=5, low=-2, c=1)], Timeframe.d1
    )
    assert not result.valid
    assert result.quarantined[0].reason is QuarantineReason.negative_price


def test_invalid_ohlc_relationship_quarantined() -> None:
    # high below open/close is impossible
    result = DataQualityValidator().validate(
        [bar(BASE, o=100, h=90, low=80, c=95)], Timeframe.d1
    )
    assert not result.valid
    assert result.quarantined[0].reason is QuarantineReason.invalid_ohlc


def test_high_below_low_quarantined() -> None:
    result = DataQualityValidator().validate(
        [bar(BASE, o=100, h=95, low=110, c=100)], Timeframe.d1
    )
    assert result.quarantined[0].reason is QuarantineReason.invalid_ohlc


def test_nan_prices_are_quarantined_as_corrupted() -> None:
    """Yahoo emits NaN OHLC rows for some ETFs.

    Every comparison against NaN is False, so without an explicit finite check the
    bar sails past the OHLC relationship rules and poisons everything computed
    over it downstream.
    """
    nan = float("nan")
    result = DataQualityValidator().validate(
        [bar(BASE, o=nan, h=nan, low=nan, c=nan)], Timeframe.d1
    )
    assert not result.valid
    assert result.quarantined[0].reason is QuarantineReason.corrupted


def test_infinite_price_is_quarantined_as_corrupted() -> None:
    result = DataQualityValidator().validate(
        [bar(BASE, h=float("inf"))], Timeframe.d1
    )
    assert result.quarantined[0].reason is QuarantineReason.corrupted


def test_zero_low_is_quarantined() -> None:
    """A real defect seen live: low=0.0 on a bar closing near 1068."""
    result = DataQualityValidator().validate(
        [bar(BASE, o=1067.9, h=1068.8, low=0.0, c=1068.8)], Timeframe.d1
    )
    assert result.quarantined[0].reason is QuarantineReason.negative_price


def test_open_above_high_is_quarantined() -> None:
    """Also seen live: open 94.57 on a bar whose high is 92.68."""
    result = DataQualityValidator().validate(
        [bar(BASE, o=94.57, h=92.68, low=92.67, c=92.67)], Timeframe.d1
    )
    assert result.quarantined[0].reason is QuarantineReason.invalid_ohlc


def test_negative_volume_quarantined() -> None:
    result = DataQualityValidator().validate([bar(BASE, v=-5)], Timeframe.d1)
    assert result.quarantined[0].reason is QuarantineReason.invalid_volume


def test_naive_timestamp_rejected_by_schema() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OHLCVBar(ts=datetime(2026, 1, 5, 10, 0), open=1, high=2, low=1, close=1, volume=1)


def test_bar_on_non_trading_day_quarantined() -> None:
    holiday = date(2026, 1, 26)
    validator = DataQualityValidator(is_known_closure=lambda d: d == holiday)
    ts = datetime(2026, 1, 26, 10, 0, tzinfo=UTC)
    result = validator.validate([bar(ts)], Timeframe.d1)
    assert not result.valid
    assert result.quarantined[0].reason is QuarantineReason.calendar_mismatch


def test_bar_is_kept_when_the_calendar_cannot_prove_a_closure() -> None:
    """Quarantine is destructive, so an unprovable closure must never reject.

    A calendar with no coverage for a date reports "not a known closure", and the
    bar has to survive — the alternative is silently deleting real history for
    every year the holiday feed does not reach.
    """
    validator = DataQualityValidator(is_known_closure=lambda d: False)
    ts = datetime(2019, 3, 4, 10, 0, tzinfo=UTC)
    result = validator.validate([bar(ts)], Timeframe.d1)
    assert len(result.valid) == 1
    assert not result.quarantined


def test_period_labelled_bars_escape_the_trading_day_check() -> None:
    """A monthly bar is stamped with the 1st, which is often a weekend.

    Applying the trading-day rule to weekly/monthly frames would quarantine
    legitimate history roughly a sixth of the time.
    """
    validator = DataQualityValidator(is_known_closure=lambda d: True)
    ts = datetime(2022, 1, 1, 0, 0, tzinfo=UTC)   # Saturday
    for timeframe in (Timeframe.w1, Timeframe.mo1):
        result = validator.validate([bar(ts)], timeframe)
        assert len(result.valid) == 1, f"{timeframe.value} must not be calendar-checked"


def test_overnight_gap_is_not_counted_as_missing_candles() -> None:
    """Session boundaries are not gaps.

    Counting the ~17h overnight break as missing 5m candles inflates the metric by
    orders of magnitude and buries genuine intraday illiquidity.
    """
    day1_close = datetime(2026, 1, 5, 15, 25, tzinfo=IST)
    day2_open = datetime(2026, 1, 6, 9, 15, tzinfo=IST)
    result = DataQualityValidator().validate(
        [bar(day1_close), bar(day2_open)], Timeframe.m5
    )
    assert len(result.valid) == 2
    assert result.missing_intervals == 0


def test_intraday_gap_detected_without_rejecting() -> None:
    bars = [
        bar(BASE),
        bar(BASE + timedelta(minutes=15)),   # 3 missing 5m intervals
    ]
    result = DataQualityValidator().validate(bars, Timeframe.m5)
    assert len(result.valid) == 2, "gaps are reported, not rejected"
    assert result.missing_intervals == 2


def test_mixed_batch_partitions_correctly() -> None:
    bars = [
        bar(BASE),
        bar(BASE + timedelta(days=1), o=-1, h=1, low=-2, c=0),   # bad
        bar(BASE + timedelta(days=2)),
    ]
    result = DataQualityValidator().validate(bars, Timeframe.d1)
    assert len(result.valid) == 2
    assert result.rejected_count == 1
