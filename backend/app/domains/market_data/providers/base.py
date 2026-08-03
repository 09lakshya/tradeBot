"""Provider abstraction (Strategy Pattern).

Every market-data source implements ``MarketDataProvider``. The rest of the
application depends only on this interface and never on a concrete provider,
so providers are swapped by configuration alone (spec §1).
"""
from abc import ABC, abstractmethod
from datetime import date

from app.domains.market_data.enums import AssetClass, Exchange, ProviderStatus, Timeframe
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVResponse,
    ProviderHealth,
)


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderTimeoutError(ProviderError):
    """Request exceeded the configured timeout."""


class ProviderRateLimitError(ProviderError):
    """Provider signalled a rate limit; caller should back off."""


class ProviderDataError(ProviderError):
    """Provider returned malformed or unusable data."""


class ProviderUnavailableError(ProviderError):
    """Provider is unreachable / down."""


class MarketDataProvider(ABC):
    """Uniform contract for all data sources.

    Implementations must be stateless with respect to application data (they may
    hold connection/session state) and must return normalized DTOs, raising the
    ``ProviderError`` hierarchy on failure so resilience wrappers can react.
    """

    #: Stable identifier used in config, caching keys, metrics, and provenance.
    name: str = "base"

    #: Exchanges this provider can serve. Used by the registry for routing/failover.
    supported_exchanges: frozenset[Exchange] = frozenset()

    #: Timeframes this provider can serve.
    supported_timeframes: frozenset[Timeframe] = frozenset()

    @abstractmethod
    def fetch_instruments(self, exchange: Exchange) -> list[InstrumentDTO]:
        """Return the tradable instrument universe for an exchange."""

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        start: date,
        end: date,
        asset_class: AssetClass | None = None,
    ) -> OHLCVResponse:
        """Return normalized OHLCV bars for a symbol over [start, end].

        ``asset_class`` is advisory but matters for symbol mapping: vendors key
        instruments differently by class. Yahoo, for instance, serves NSE equities
        as ``TCS.NS`` but indices as ``^NSEI`` — and ``NIFTY 50.NS`` does not fail,
        it silently resolves to an unrelated instrument. Adapters that cannot map a
        symbol for its class must raise rather than fall back to a guess.
        """

    @abstractmethod
    def fetch_corporate_actions(
        self, symbol: str, exchange: Exchange
    ) -> list[CorporateActionDTO]:
        """Return corporate actions known for a symbol."""

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        """Cheap liveness/latency probe used by monitoring and failover."""

    # --- shared helpers -------------------------------------------------
    def can_serve(self, exchange: Exchange, timeframe: Timeframe) -> bool:
        exch_ok = not self.supported_exchanges or exchange in self.supported_exchanges
        tf_ok = not self.supported_timeframes or timeframe in self.supported_timeframes
        return exch_ok and tf_ok

    def _status_from_latency(self, latency_ms: float, degraded_ms: float = 1500) -> ProviderStatus:
        return ProviderStatus.up if latency_ms < degraded_ms else ProviderStatus.degraded
