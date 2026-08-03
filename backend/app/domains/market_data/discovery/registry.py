"""Discovery source registry.

Sources register by name and are built lazily, mirroring the price-provider
registry. Adding an asset class or a new exchange is a registration, not a
change to the discovery service.
"""
from __future__ import annotations

from collections.abc import Callable

from app.domains.market_data.discovery.base import ExchangeHttpClient, InstrumentSource
from app.domains.market_data.enums import AssetClass, Exchange

SourceFactory = Callable[[ExchangeHttpClient], InstrumentSource]

_SOURCES: dict[str, SourceFactory] = {}


def register_source(name: str, factory: SourceFactory) -> None:
    _SOURCES[name] = factory


def available_sources() -> list[str]:
    _register_builtin()
    return sorted(_SOURCES)


def _register_builtin() -> None:
    if _SOURCES:
        return

    def _nse_equity(client: ExchangeHttpClient) -> InstrumentSource:
        from app.domains.market_data.discovery.nse import NSEEquitySource
        return NSEEquitySource(client)

    def _nse_etf(client: ExchangeHttpClient) -> InstrumentSource:
        from app.domains.market_data.discovery.nse import NSEEtfSource
        return NSEEtfSource(client)

    def _nse_index(client: ExchangeHttpClient) -> InstrumentSource:
        from app.domains.market_data.discovery.nse import NSEIndexSource
        return NSEIndexSource(client)

    def _bse_equity(client: ExchangeHttpClient) -> InstrumentSource:
        from app.domains.market_data.discovery.bse import BSEEquitySource
        return BSEEquitySource(client)

    register_source("nse_equity", _nse_equity)
    register_source("nse_etf", _nse_etf)
    register_source("nse_index", _nse_index)
    register_source("bse_equity", _bse_equity)


def build_sources(
    names: list[str] | None = None,
    exchanges: set[Exchange] | None = None,
    asset_classes: set[AssetClass] | None = None,
    client: ExchangeHttpClient | None = None,
) -> list[InstrumentSource]:
    """Build the requested sources, optionally filtered by exchange/asset class.

    Sources share one HTTP client so the cookie handshake each exchange requires
    is paid once per run rather than once per source.
    """
    _register_builtin()
    shared = client or ExchangeHttpClient()
    selected = names if names is not None else sorted(_SOURCES)

    built: list[InstrumentSource] = []
    for name in selected:
        if name not in _SOURCES:
            raise KeyError(f"unknown discovery source: {name!r}")
        source = _SOURCES[name](shared)
        if exchanges and source.exchange not in exchanges:
            continue
        if asset_classes and source.asset_class not in asset_classes:
            continue
        built.append(source)
    return built
