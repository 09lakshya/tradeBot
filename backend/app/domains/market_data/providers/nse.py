"""Official NSE provider (future scaffold).

Placeholder for a direct NSE data feed once access/permissions are in place.
Registered on build-out; intentionally not in the default registry yet.
"""
from app.domains.market_data.enums import Exchange, Timeframe
from app.domains.market_data.providers._stub import HttpProviderScaffold


class NSEProvider(HttpProviderScaffold):
    name = "nse"
    api_key_setting = ""   # auth model TBD (session/cookie vs. licensed feed)
    supported_exchanges = frozenset({Exchange.NSE})
    supported_timeframes = frozenset({
        Timeframe.m1, Timeframe.m5, Timeframe.m15, Timeframe.m30, Timeframe.h1, Timeframe.d1,
    })
