"""Alpha Vantage provider (scaffold — implement HTTP client to activate)."""
from app.domains.market_data.enums import Exchange, Timeframe
from app.domains.market_data.providers._stub import HttpProviderScaffold


class AlphaVantageProvider(HttpProviderScaffold):
    name = "alpha_vantage"
    api_key_setting = "alpha_vantage_api_key"
    supported_exchanges = frozenset({Exchange.NSE, Exchange.BSE})
    supported_timeframes = frozenset({
        Timeframe.m1, Timeframe.m5, Timeframe.m15, Timeframe.m30, Timeframe.h1, Timeframe.d1,
    })
