"""Deterministic in-memory provider for tests and local development.

Generates a reproducible random-walk OHLCV series (seeded), and can be configured
to inject failures — timeouts, rate limits, bad data — to exercise resilience,
retry, and failover paths without any network.
"""
from datetime import UTC, date, datetime, timedelta

from app.domains.market_data.enums import (
    AssetClass,
    CorporateActionType,
    Exchange,
    InstrumentType,
    ProviderStatus,
    Timeframe,
)
from app.domains.market_data.providers.base import (
    MarketDataProvider,
    ProviderDataError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVBar,
    OHLCVResponse,
    ProviderHealth,
)


class MockProvider(MarketDataProvider):
    name = "mock"
    supported_exchanges = frozenset({Exchange.NSE, Exchange.BSE})
    supported_timeframes = frozenset(Timeframe)

    def __init__(
        self,
        *,
        fail_first: int = 0,
        fail_kind: str = "timeout",
        seed: int = 42,
        start_price: float = 100.0,
    ) -> None:
        # `fail_first` transient failures before succeeding — for retry tests.
        self._fail_first = fail_first
        self._fail_kind = fail_kind
        self._calls = 0
        self._seed = seed
        self._start_price = start_price

    def _maybe_fail(self) -> None:
        self._calls += 1
        if self._calls <= self._fail_first:
            if self._fail_kind == "rate_limit":
                raise ProviderRateLimitError("mock rate limit")
            if self._fail_kind == "bad_data":
                raise ProviderDataError("mock bad data")
            raise ProviderTimeoutError("mock timeout")

    def fetch_instruments(self, exchange: Exchange) -> list[InstrumentDTO]:
        self._maybe_fail()
        return [
            InstrumentDTO(
                trading_symbol="RELIANCE", name="Reliance Industries Ltd",
                exchange=exchange, asset_class=AssetClass.equity,
                instrument_type=InstrumentType.eq, isin="INE002A01018",
                nse_symbol="RELIANCE", bse_symbol="500325", sector="Energy",
            ),
            InstrumentDTO(
                trading_symbol="TCS", name="Tata Consultancy Services Ltd",
                exchange=exchange, isin="INE467B01029",
                nse_symbol="TCS", bse_symbol="532540", sector="IT",
            ),
        ]

    def fetch_ohlcv(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe, start: date, end: date,
        asset_class: AssetClass | None = None,
    ) -> OHLCVResponse:
        self._maybe_fail()
        bars: list[OHLCVBar] = []
        # Simple deterministic LCG so tests get identical, tunable output.
        state = (self._seed + hash(symbol)) & 0xFFFFFFFF
        price = self._start_price
        cursor = datetime(start.year, start.month, start.day, tzinfo=UTC)
        end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC)
        step = timedelta(seconds=timeframe.seconds)
        while cursor <= end_dt:
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            drift = ((state % 1000) / 1000.0 - 0.5) * 2.0  # [-1, 1]
            open_p = price
            close_p = max(1.0, price + drift)
            high_p = max(open_p, close_p) + abs(drift) * 0.5
            low_p = min(open_p, close_p) - abs(drift) * 0.5
            bars.append(OHLCVBar(
                ts=cursor, open=round(open_p, 2), high=round(high_p, 2),
                low=round(low_p, 2), close=round(close_p, 2),
                volume=1000 + (state % 5000), adjusted_close=round(close_p, 2),
            ))
            price = close_p
            cursor += step
        return OHLCVResponse(
            instrument_symbol=symbol, exchange=exchange,
            timeframe=timeframe, bars=bars, provider=self.name,
        )

    def fetch_corporate_actions(
        self, symbol: str, exchange: Exchange
    ) -> list[CorporateActionDTO]:
        self._maybe_fail()
        return [
            CorporateActionDTO(
                action_type=CorporateActionType.split,
                ex_date=date(2023, 1, 20), ratio_from=1, ratio_to=2,
            ),
            CorporateActionDTO(
                action_type=CorporateActionType.dividend,
                ex_date=date(2023, 7, 15), amount=8.0,
            ),
        ]

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name, status=ProviderStatus.up,
            latency_ms=1.0, checked_at=datetime.now(UTC),
        )
