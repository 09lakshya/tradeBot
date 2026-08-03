"""Enumerations for the market data domain.

Designed for multi-asset expansion (spec §9): asset classes and instrument types
are open enums that grow without schema rewrites, because storage keys on the
enum *value*, not on exchange-specific branching.
"""
import enum


class Exchange(str, enum.Enum):
    NSE = "NSE"
    BSE = "BSE"
    # Future: NYSE, NASDAQ, BINANCE, MCX, ... — added without schema change.


class AssetClass(str, enum.Enum):
    equity = "equity"
    etf = "etf"
    # Shadows `str.index`; harmless for Enum members (attribute access resolves to
    # the member), and the wire/DB value must stay "index".
    index = "index"  # type: ignore[assignment]
    mutual_fund = "mutual_fund"
    future = "future"
    option = "option"
    commodity = "commodity"
    forex = "forex"
    crypto = "crypto"


class InstrumentType(str, enum.Enum):
    """Finer-grained than AssetClass (e.g. equity can be EQ/BE series)."""
    eq = "EQ"
    etf = "ETF"
    index = "INDEX"  # type: ignore[assignment]  # shadows str.index; see AssetClass
    mutual_fund = "MF"
    futures = "FUT"
    options = "OPT"
    commodity = "COMM"
    currency = "CUR"
    crypto = "CRYPTO"


class MarketCapCategory(str, enum.Enum):
    large = "large"
    mid = "mid"
    small = "small"
    micro = "micro"
    unknown = "unknown"


class Timeframe(str, enum.Enum):
    m1 = "1m"
    m5 = "5m"
    m15 = "15m"
    m30 = "30m"
    h1 = "1h"
    h4 = "4h"
    d1 = "1d"
    w1 = "1w"
    mo1 = "1mo"

    @property
    def seconds(self) -> int:
        return {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400,
            "1w": 604800, "1mo": 2592000,
        }[self.value]

    @property
    def is_intraday(self) -> bool:
        return self.seconds < 86400


class CorporateActionType(str, enum.Enum):
    dividend = "dividend"
    split = "split"  # type: ignore[assignment]  # shadows str.split; see AssetClass
    bonus = "bonus"
    rights = "rights"
    buyback = "buyback"
    merger = "merger"
    spinoff = "spinoff"
    symbol_change = "symbol_change"
    delisting = "delisting"


class SessionType(str, enum.Enum):
    normal = "normal"
    holiday = "holiday"
    half_day = "half_day"
    special = "special"          # e.g. settlement / testing sessions
    muhurat = "muhurat"          # Diwali ceremonial session
    unexpected_closure = "unexpected_closure"


class ProviderStatus(str, enum.Enum):
    up = "up"
    degraded = "degraded"
    down = "down"


class QuarantineReason(str, enum.Enum):
    duplicate = "duplicate"
    missing_timestamp = "missing_timestamp"
    negative_price = "negative_price"
    invalid_ohlc = "invalid_ohlc"           # e.g. high < low
    invalid_volume = "invalid_volume"
    timezone_mismatch = "timezone_mismatch"
    calendar_mismatch = "calendar_mismatch"  # bar on a non-trading day
    corrupted = "corrupted"
