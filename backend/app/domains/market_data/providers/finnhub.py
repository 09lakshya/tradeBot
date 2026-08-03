"""Finnhub provider (scaffold — implement HTTP client to activate)."""
from app.domains.market_data.enums import Exchange, Timeframe
from app.domains.market_data.providers._stub import HttpProviderScaffold


class FinnhubProvider(HttpProviderScaffold):
    name = "finnhub"
    api_key_setting = "finnhub_api_key"
    supported_exchanges = frozenset({Exchange.NSE, Exchange.BSE})
    supported_timeframes = frozenset({
        Timeframe.m1, Timeframe.m5, Timeframe.m15, Timeframe.m30, Timeframe.h1, Timeframe.d1,
    })
