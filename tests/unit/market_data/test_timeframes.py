"""Multi-timeframe architecture: all intervals are first-class, not daily-special."""
import pytest

from app.domains.market_data.enums import Timeframe

REQUIRED = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]


def test_all_required_timeframes_exist() -> None:
    values = {t.value for t in Timeframe}
    assert set(REQUIRED).issubset(values)


@pytest.mark.parametrize(
    ("tf", "seconds"),
    [
        (Timeframe.m1, 60), (Timeframe.m5, 300), (Timeframe.m15, 900),
        (Timeframe.m30, 1800), (Timeframe.h1, 3600), (Timeframe.h4, 14400),
        (Timeframe.d1, 86400), (Timeframe.w1, 604800),
    ],
)
def test_timeframe_seconds(tf: Timeframe, seconds: int) -> None:
    assert tf.seconds == seconds


def test_intraday_classification() -> None:
    for tf in (Timeframe.m1, Timeframe.m5, Timeframe.m15, Timeframe.m30,
               Timeframe.h1, Timeframe.h4):
        assert tf.is_intraday is True
    for tf in (Timeframe.d1, Timeframe.w1, Timeframe.mo1):
        assert tf.is_intraday is False


def test_every_timeframe_has_a_duration() -> None:
    for tf in Timeframe:
        assert tf.seconds > 0
