"""Shared scaffold for providers that are wired but not yet implemented.

These are real classes conforming to ``MarketDataProvider`` so the registry,
failover, and config-switching all work today. Each raises a clear, typed error
until its HTTP client is implemented — never a silent wrong answer. When you build
one out, replace the method bodies; the interface and registration stay put.
"""
from datetime import UTC, date, datetime

from app.core.config import settings
from app.domains.market_data.enums import AssetClass, Exchange, ProviderStatus, Timeframe
from app.domains.market_data.providers.base import (
    MarketDataProvider,
    ProviderUnavailableError,
)
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVResponse,
    ProviderHealth,
)


class HttpProviderScaffold(MarketDataProvider):
    """Base for external HTTP providers pending implementation."""

    api_key_setting: str = ""   # attribute name on Settings holding the key

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._api_key = getattr(settings, self.api_key_setting, "") if self.api_key_setting else ""

    def _not_ready(self) -> ProviderUnavailableError:
        if self.api_key_setting and not self._api_key:
            return ProviderUnavailableError(
                f"{self.name}: missing API key ({self.api_key_setting})"
            )
        return ProviderUnavailableError(f"{self.name}: adapter not yet implemented")

    def fetch_instruments(self, exchange: Exchange) -> list[InstrumentDTO]:
        raise self._not_ready()

    def fetch_ohlcv(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe, start: date, end: date,
        asset_class: AssetClass | None = None,
    ) -> OHLCVResponse:
        raise self._not_ready()

    def fetch_corporate_actions(
        self, symbol: str, exchange: Exchange
    ) -> list[CorporateActionDTO]:
        raise self._not_ready()

    def health_check(self) -> ProviderHealth:
        configured = bool(self._api_key) if self.api_key_setting else False
        return ProviderHealth(
            provider=self.name,
            status=ProviderStatus.up if configured else ProviderStatus.down,
            detail=None if configured else "not configured / not implemented",
            checked_at=datetime.now(UTC),
        )
