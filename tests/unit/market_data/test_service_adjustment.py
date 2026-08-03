"""Provider-aware corporate-action adjustment in the ingestion service.

The headline regression: a provider that already split-adjusts its Close (Yahoo)
must not have that split applied a second time. Double-adjustment leaves a
discontinuity at every historical split and silently corrupts every backtest
built on the series — the exact data-leakage failure the project treats as
existential.
"""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.enums import CorporateActionType, Exchange, Timeframe
from app.domains.market_data.providers.base import MarketDataProvider
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVBar,
    OHLCVResponse,
    ProviderHealth,
)
from app.domains.market_data.service import MarketDataService

SPLIT_DATE = date(2026, 3, 2)


def _bars(pre_split_close: float, post_split_close: float) -> list[OHLCVBar]:
    """Ten daily bars straddling the split, already continuous (split folded in)."""
    out = []
    start = datetime(2026, 2, 23, tzinfo=UTC)
    for i in range(10):
        ts = start + timedelta(days=i)
        close = pre_split_close if ts.date() < SPLIT_DATE else post_split_close
        out.append(OHLCVBar(ts=ts, open=close, high=close * 1.01,
                            low=close * 0.99, close=close, volume=1000))
    return out


class PreAdjustedProvider(MarketDataProvider):
    """Mimics Yahoo: returns a split-continuous Close and declares it pre-adjusted."""

    name = "pre_adjusted"
    supported_exchanges = frozenset({Exchange.NSE})
    supported_timeframes = frozenset({Timeframe.d1})

    def fetch_instruments(self, exchange):  # noqa: ANN001, ANN201
        return []

    def fetch_ohlcv(self, symbol, exchange, timeframe, start, end, asset_class=None):  # noqa: ANN001, ANN201
        return OHLCVResponse(
            instrument_symbol=symbol, exchange=exchange, timeframe=timeframe,
            bars=_bars(500.0, 505.0), provider=self.name,
            pre_adjusted=frozenset({CorporateActionType.split}),
        )

    def fetch_corporate_actions(self, symbol, exchange):  # noqa: ANN001, ANN201
        return [CorporateActionDTO(
            action_type=CorporateActionType.split, ex_date=SPLIT_DATE,
            ratio_from=1.0, ratio_to=2.0,
        )]

    def health_check(self):  # noqa: ANN201
        return ProviderHealth(provider=self.name, status="up", checked_at=datetime.now(UTC))


class RawProvider(PreAdjustedProvider):
    """Mimics a raw feed: Close halves across the split, nothing pre-adjusted."""

    name = "raw"

    def fetch_ohlcv(self, symbol, exchange, timeframe, start, end, asset_class=None):  # noqa: ANN001, ANN201
        return OHLCVResponse(
            instrument_symbol=symbol, exchange=exchange, timeframe=timeframe,
            bars=_bars(1000.0, 505.0), provider=self.name, pre_adjusted=frozenset(),
        )


def _service(db, provider) -> MarketDataService:  # noqa: ANN001
    svc = MarketDataService(db=db, provider=provider, calendar=MarketCalendarService(db))
    svc.get_or_create_instrument(InstrumentDTO(
        trading_symbol="X", name="X Ltd", exchange=Exchange.NSE, isin="INE000000001",
    ))
    svc.sync_corporate_actions("X", Exchange.NSE)
    return svc


def _continuity_gap(bars: list[OHLCVBar]) -> float:
    bars = sorted(bars, key=lambda b: b.ts)
    before = [b for b in bars if b.ts.date() < SPLIT_DATE]
    after = [b for b in bars if b.ts.date() >= SPLIT_DATE]
    return abs(after[0].close / before[-1].close - 1.0)


def test_pre_adjusted_split_is_not_applied_again(db) -> None:  # noqa: ANN001
    """The regression guard: an already-adjusted series stays continuous."""
    svc = _service(db, PreAdjustedProvider())
    svc.sync_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    stored = svc.get_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    # 500 -> 505 across the split: a ~1% move, NOT a halving. If the split were
    # re-applied the pre-split closes would drop to 250 and the gap would be ~1.0.
    assert _continuity_gap(stored) < 0.05


def test_raw_feed_still_gets_the_split_applied(db) -> None:  # noqa: ANN001
    """The other half of the contract: a raw feed must still be adjusted."""
    svc = _service(db, RawProvider())
    svc.sync_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    stored = svc.get_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    # Raw pre-split close 1000 must be halved to ~500 so it meets the post-split
    # 505 continuously — the engine's job when the provider did not pre-adjust.
    assert _continuity_gap(stored) < 0.05


@pytest.mark.parametrize("provider", [PreAdjustedProvider(), RawProvider()])
def test_series_is_continuous_either_way(db, provider) -> None:  # noqa: ANN001
    """Whichever provider serves, the stored series is continuous across the split.

    This is the property the whole mechanism exists to guarantee, independent of
    which side pre-applied the adjustment.
    """
    svc = _service(db, provider)
    svc.sync_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    stored = svc.get_ohlcv("X", Exchange.NSE, Timeframe.d1, date(2026, 2, 23), date(2026, 3, 4))
    assert _continuity_gap(stored) < 0.05
