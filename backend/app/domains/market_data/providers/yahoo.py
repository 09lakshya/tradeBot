"""Yahoo Finance provider — the initial real adapter (never a permanent dependency).

Uses yfinance. NSE symbols map to ``<SYMBOL>.NS`` and BSE to ``<SYMBOL>.BO``.
Corporate actions (dividends, splits) come from yfinance's actions feed; richer
action types require a dedicated provider and are returned empty here rather than
guessed.
"""
from datetime import UTC, date, datetime
from typing import Any

from app.core.logging import get_logger
from app.domains.market_data.enums import (
    AssetClass,
    CorporateActionType,
    Exchange,
    ProviderStatus,
    Timeframe,
)
from app.domains.market_data.providers.base import (
    MarketDataProvider,
    ProviderDataError,
    ProviderUnavailableError,
)
from app.domains.market_data.resampling import DERIVED_FROM, resample
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVBar,
    OHLCVResponse,
    ProviderHealth,
)
from app.domains.market_data.sessions import exchange_timezone

log = get_logger(__name__)

#: Action types Yahoo has already folded into the Close it returns.
_PRE_ADJUSTED = frozenset({CorporateActionType.split, CorporateActionType.bonus})

_SUFFIX = {Exchange.NSE: ".NS", Exchange.BSE: ".BO"}

#: Indices do not follow the ``<SYMBOL><suffix>`` convention — Yahoo publishes them
#: under its own identifiers. This mapping is exhaustive for what Yahoo actually
#: serves; NSE publishes ~139 indices and only these resolve.
#:
#: The map is not a convenience. ``NIFTY 50.NS`` returns *nothing*, but several
#: index names collide with tradable NSE tickers — ``BHARATBOND-APR30.NS`` is an
#: ETF — so guessing the suffix silently returns a different instrument's prices.
#: Unmapped indices are refused instead.
_INDEX_TICKERS = {
    "NIFTY 50": "^NSEI",
    "NIFTY NEXT 50": "^NSMIDCP",
    "NIFTY 100": "^CNX100",
    "NIFTY 500": "^CRSLDX",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY MIDCAP 100": "NIFTY_MIDCAP_100.NS",
    "NIFTY FIN SERVICE": "NIFTY_FIN_SERVICE.NS",
    "INDIA VIX": "^INDIAVIX",
    "NIFTY IT": "^CNXIT",
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY METAL": "^CNXMETAL",
    "NIFTY REALTY": "^CNXREALTY",
    "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY PSU BANK": "^CNXPSUBANK",
    "NIFTY MEDIA": "^CNXMEDIA",
    "NIFTY INFRA": "^CNXINFRA",
    "NIFTY COMMODITIES": "^CNXCMDT",
    "NIFTY CONSUMPTION": "^CNXCONSUM",
    "NIFTY MNC": "^CNXMNC",
    "NIFTY PSE": "^CNXPSE",
    "NIFTY SERV SECTOR": "^CNXSERVICE",
    "SENSEX": "^BSESN",
}
_INTERVAL = {
    Timeframe.m1: "1m", Timeframe.m5: "5m", Timeframe.m15: "15m",
    Timeframe.m30: "30m", Timeframe.h1: "60m", Timeframe.d1: "1d",
    Timeframe.w1: "1wk", Timeframe.mo1: "1mo",
}


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"
    supported_exchanges = frozenset({Exchange.NSE, Exchange.BSE})
    # 4h has no Yahoo interval and no natural boundary in a 6h15m Indian session;
    # it is aggregated from 1h so the platform's timeframe surface stays complete
    # regardless of what any single vendor happens to publish.
    supported_timeframes = frozenset(_INTERVAL) | frozenset(DERIVED_FROM)

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def _yf(self) -> Any:  # lazy import so tests/CI don't need the dep
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailableError("yfinance not installed") from exc
        return yf

    def _ticker(
        self, symbol: str, exchange: Exchange, asset_class: AssetClass | None = None
    ) -> str:
        if asset_class is AssetClass.index:
            mapped = _INDEX_TICKERS.get(symbol.upper())
            if mapped is None:
                raise ProviderDataError(
                    f"yahoo has no index mapping for {symbol!r}; refusing to guess a "
                    "ticker that may resolve to a different instrument"
                )
            return mapped
        return f"{symbol}{_SUFFIX[exchange]}"

    def fetch_instruments(self, exchange: Exchange) -> list[InstrumentDTO]:
        # Yahoo has no clean instrument-universe endpoint; the Instrument Master is
        # seeded from an official exchange list and enriched here per-symbol instead.
        raise ProviderDataError(
            "yahoo does not expose an instrument universe; seed the master from the exchange"
        )

    def fetch_ohlcv(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe, start: date, end: date,
        asset_class: AssetClass | None = None,
    ) -> OHLCVResponse:
        if timeframe in DERIVED_FROM:
            source_tf = DERIVED_FROM[timeframe]
            base = self.fetch_ohlcv(symbol, exchange, source_tf, start, end, asset_class)
            return base.model_copy(update={
                "timeframe": timeframe,
                "bars": resample(
                    base.bars, source_tf, timeframe, exchange_timezone(exchange)
                ),
            })
        if timeframe not in _INTERVAL:
            raise ProviderDataError(f"yahoo cannot serve timeframe {timeframe.value}")
        yf = self._yf()
        ticker = self._ticker(symbol, exchange, asset_class)
        try:
            df = yf.Ticker(ticker).history(
                start=start.isoformat(), end=end.isoformat(),
                interval=_INTERVAL[timeframe], auto_adjust=False, timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001 - normalize any yfinance/network error
            raise ProviderUnavailableError(f"yahoo fetch failed for {ticker}: {exc}") from exc
        if df is None or df.empty:
            raise ProviderDataError(f"yahoo returned no data for {ticker}")

        bars: list[OHLCVBar] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            bars.append(OHLCVBar(
                ts=ts,
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(row["Close"]),
                volume=int(row["Volume"]),
                adjusted_close=float(row["Adj Close"]) if "Adj Close" in row else None,
            ))
        return OHLCVResponse(
            instrument_symbol=symbol, exchange=exchange,
            timeframe=timeframe, bars=bars, provider=self.name,
            # Yahoo back-adjusts share-count events (splits, bonuses) into the
            # Close it returns, even with auto_adjust=False. Re-applying them
            # downstream would double-adjust; dividends are NOT pre-applied here
            # (that is what Adj Close adds) so they remain the engine's job.
            pre_adjusted=_PRE_ADJUSTED,
        )

    def fetch_corporate_actions(
        self, symbol: str, exchange: Exchange
    ) -> list[CorporateActionDTO]:
        yf = self._yf()
        ticker = self._ticker(symbol, exchange)
        try:
            t = yf.Ticker(ticker)
            actions = []
            for ex_dt, amount in getattr(t, "dividends", {}).items():
                actions.append(CorporateActionDTO(
                    action_type=CorporateActionType.dividend,
                    ex_date=ex_dt.date(), amount=float(amount),
                ))
            for ex_dt, ratio in getattr(t, "splits", {}).items():
                actions.append(CorporateActionDTO(
                    action_type=CorporateActionType.split,
                    ex_date=ex_dt.date(), ratio_from=1.0, ratio_to=float(ratio),
                ))
            return actions
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailableError(f"yahoo actions failed for {ticker}: {exc}") from exc

    def health_check(self) -> ProviderHealth:
        started = datetime.now(UTC)
        try:
            yf = self._yf()
            df = yf.Ticker("RELIANCE.NS").history(period="1d", timeout=self._timeout)
            latency = (datetime.now(UTC) - started).total_seconds() * 1000
            healthy = df is not None and not df.empty
            status = ProviderStatus.up if healthy else ProviderStatus.degraded
            return ProviderHealth(
                provider=self.name, status=status,
                latency_ms=round(latency, 1), checked_at=datetime.now(UTC),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.name, status=ProviderStatus.down,
                detail=str(exc), checked_at=datetime.now(UTC),
            )
