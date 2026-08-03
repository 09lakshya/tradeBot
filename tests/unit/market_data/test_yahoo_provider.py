"""Yahoo adapter: symbol mapping, normalization, and error translation.

yfinance is stubbed via ``sys.modules`` so these run offline and deterministically.
What matters here is that the adapter maps Indian symbols correctly, normalizes
into our DTOs, and translates *every* upstream failure into the ProviderError
hierarchy the resilience layer understands.
"""
import sys
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.domains.market_data.enums import (
    AssetClass,
    CorporateActionType,
    Exchange,
    ProviderStatus,
    Timeframe,
)
from app.domains.market_data.providers.base import (
    ProviderDataError,
    ProviderUnavailableError,
)
from app.domains.market_data.providers.yahoo import YahooFinanceProvider

START, END = date(2026, 1, 5), date(2026, 1, 9)


def _frame() -> pd.DataFrame:
    idx = pd.to_datetime(
        ["2026-01-05", "2026-01-06", "2026-01-07"], utc=True
    )
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0, 104.0],
            "High": [105.0, 106.0, 108.0],
            "Low": [99.0, 101.0, 103.0],
            "Close": [102.0, 104.0, 106.0],
            "Adj Close": [102.0, 104.0, 106.0],
            "Volume": [1000, 1100, 1200],
        },
        index=idx,
    )


class _FakeTicker:
    def __init__(self, frame=None, raises=None, dividends=None, splits=None):  # noqa: ANN001
        self._frame = frame if frame is not None else _frame()
        self._raises = raises
        self.dividends = dividends or {}
        self.splits = splits or {}

    def history(self, **kwargs):  # noqa: ANN003, ANN201
        if self._raises:
            raise self._raises
        return self._frame


@pytest.fixture
def fake_yf(monkeypatch):  # noqa: ANN001, ANN201
    """Install a stub yfinance module; tests set ``module.Ticker``."""
    module = SimpleNamespace(Ticker=lambda symbol: _FakeTicker())
    monkeypatch.setitem(sys.modules, "yfinance", module)
    return module


def test_nse_symbol_gets_ns_suffix(fake_yf) -> None:  # noqa: ANN001
    seen = {}

    def ticker(symbol):  # noqa: ANN001, ANN202
        seen["symbol"] = symbol
        return _FakeTicker()

    fake_yf.Ticker = ticker
    YahooFinanceProvider().fetch_ohlcv("RELIANCE", Exchange.NSE, Timeframe.d1, START, END)
    assert seen["symbol"] == "RELIANCE.NS"


def test_bse_symbol_gets_bo_suffix(fake_yf) -> None:  # noqa: ANN001
    seen = {}

    def ticker(symbol):  # noqa: ANN001, ANN202
        seen["symbol"] = symbol
        return _FakeTicker()

    fake_yf.Ticker = ticker
    YahooFinanceProvider().fetch_ohlcv("500325", Exchange.BSE, Timeframe.d1, START, END)
    assert seen["symbol"] == "500325.BO"


def test_bars_are_normalized_with_tz_aware_timestamps(fake_yf) -> None:  # noqa: ANN001
    resp = YahooFinanceProvider().fetch_ohlcv(
        "TCS", Exchange.NSE, Timeframe.d1, START, END
    )
    assert len(resp.bars) == 3
    assert resp.provider == "yahoo"
    for b in resp.bars:
        assert b.ts.tzinfo is not None
        assert b.high >= b.low
    assert resp.bars[0].close == 102.0
    assert resp.bars[0].adjusted_close == 102.0


def test_empty_frame_raises_data_error(fake_yf) -> None:  # noqa: ANN001
    fake_yf.Ticker = lambda symbol: _FakeTicker(frame=pd.DataFrame())
    with pytest.raises(ProviderDataError):
        YahooFinanceProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)


def test_network_error_becomes_provider_unavailable(fake_yf) -> None:  # noqa: ANN001
    fake_yf.Ticker = lambda symbol: _FakeTicker(raises=OSError("connection reset"))
    with pytest.raises(ProviderUnavailableError):
        YahooFinanceProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)


def test_four_hour_is_derived_from_hourly(fake_yf) -> None:  # noqa: ANN001
    """Yahoo has no 4h interval, so the adapter aggregates it from 1h.

    Four hourly bars inside one session must fold into a single 4h bar whose OHLC
    is the envelope of its constituents — not be refused, and not be mis-served.
    """
    idx = pd.to_datetime(
        [
            "2026-01-05 09:15", "2026-01-05 10:15",
            "2026-01-05 11:15", "2026-01-05 12:15",
        ]
    ).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 102.0, 101.0, 103.0],
            "High": [103.0, 104.0, 102.0, 107.0],
            "Low": [99.0, 100.0, 98.0, 102.0],
            "Close": [102.0, 101.0, 103.0, 106.0],
            "Adj Close": [102.0, 101.0, 103.0, 106.0],
            "Volume": [10, 20, 30, 40],
        },
        index=idx,
    )
    fake_yf.Ticker = lambda symbol: _FakeTicker(frame=frame)
    resp = YahooFinanceProvider().fetch_ohlcv(
        "TCS", Exchange.NSE, Timeframe.h4, START, END
    )
    assert resp.timeframe is Timeframe.h4
    assert len(resp.bars) == 1
    bar = resp.bars[0]
    assert (bar.open, bar.high, bar.low, bar.close) == (100.0, 107.0, 98.0, 106.0)
    assert bar.volume == 100


def test_four_hour_is_advertised_as_supported() -> None:
    provider = YahooFinanceProvider()
    assert Timeframe.h4 in provider.supported_timeframes
    assert Timeframe.d1 in provider.supported_timeframes


def test_index_uses_yahoos_own_identifier(fake_yf) -> None:  # noqa: ANN001
    seen = {}

    def ticker(symbol):  # noqa: ANN001, ANN202
        seen["symbol"] = symbol
        return _FakeTicker()

    fake_yf.Ticker = ticker
    YahooFinanceProvider().fetch_ohlcv(
        "NIFTY 50", Exchange.NSE, Timeframe.d1, START, END, AssetClass.index
    )
    assert seen["symbol"] == "^NSEI"


def test_unmapped_index_is_refused_rather_than_suffixed(fake_yf) -> None:  # noqa: ANN001
    """Guessing `<NAME>.NS` for an index is worse than failing.

    Several NSE index names collide with tradable NSE tickers — `BHARATBOND-APR30`
    is both a bond index and an ETF — so the guess returns a *different
    instrument's* prices with no error anywhere.
    """
    with pytest.raises(ProviderDataError, match="no index mapping"):
        YahooFinanceProvider().fetch_ohlcv(
            "BHARATBOND-APR30", Exchange.NSE, Timeframe.d1, START, END, AssetClass.index
        )


def test_equity_mapping_is_unaffected_by_asset_class(fake_yf) -> None:  # noqa: ANN001
    seen = {}

    def ticker(symbol):  # noqa: ANN001, ANN202
        seen["symbol"] = symbol
        return _FakeTicker()

    fake_yf.Ticker = ticker
    YahooFinanceProvider().fetch_ohlcv(
        "TCS", Exchange.NSE, Timeframe.d1, START, END, AssetClass.equity
    )
    assert seen["symbol"] == "TCS.NS"


def test_instrument_universe_is_refused_not_faked(fake_yf) -> None:  # noqa: ANN001
    with pytest.raises(ProviderDataError):
        YahooFinanceProvider().fetch_instruments(Exchange.NSE)


def test_corporate_actions_mapped(fake_yf) -> None:  # noqa: ANN001
    ex = pd.Timestamp("2026-01-08", tz="UTC")
    fake_yf.Ticker = lambda symbol: _FakeTicker(
        dividends={ex: 8.0}, splits={ex: 2.0}
    )
    actions = YahooFinanceProvider().fetch_corporate_actions("TCS", Exchange.NSE)
    kinds = {a.action_type for a in actions}
    assert CorporateActionType.dividend in kinds
    assert CorporateActionType.split in kinds
    split = next(a for a in actions if a.action_type is CorporateActionType.split)
    assert split.ratio_to == 2.0
    assert split.ex_date == date(2026, 1, 8)


def test_health_check_up_when_data_returned(fake_yf) -> None:  # noqa: ANN001
    health = YahooFinanceProvider().health_check()
    assert health.status is ProviderStatus.up
    assert health.provider == "yahoo"


def test_health_check_down_on_error(fake_yf) -> None:  # noqa: ANN001
    fake_yf.Ticker = lambda symbol: _FakeTicker(raises=OSError("down"))
    health = YahooFinanceProvider().health_check()
    assert health.status is ProviderStatus.down
    assert health.detail


def test_missing_yfinance_dependency_is_typed(monkeypatch) -> None:  # noqa: ANN001
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001, ANN202
        if name == "yfinance":
            raise ImportError("no yfinance")
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, "yfinance", None)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ProviderUnavailableError, match="yfinance"):
        YahooFinanceProvider().fetch_corporate_actions("TCS", Exchange.NSE)


def test_naive_timestamps_are_made_utc_aware(fake_yf) -> None:  # noqa: ANN001
    frame = _frame()
    frame.index = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])  # tz-naive
    fake_yf.Ticker = lambda symbol: _FakeTicker(frame=frame)
    resp = YahooFinanceProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    assert all(b.ts.tzinfo is not None for b in resp.bars)
    assert resp.bars[0].ts == datetime(2026, 1, 5, tzinfo=timezone.utc)
