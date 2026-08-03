"""Normalized DTOs exchanged between providers, services, and the API.

Providers return these — never ORM objects — so the persistence layer stays the
single writer and adapters remain swappable and independently testable.
"""
import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domains.market_data.enums import (
    AssetClass,
    CorporateActionType,
    Exchange,
    InstrumentType,
    ProviderStatus,
    Timeframe,
)

#: ISO 6166: two-letter country code, nine alphanumerics, one check digit.
_ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

#: Placeholder values exchanges publish where an ISIN is unavailable.
_ISIN_SENTINELS = frozenset({"NA", "N.A.", "N/A", "NIL", "NONE", "-", "0", "--"})


class InstrumentDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    trading_symbol: str
    name: str
    exchange: Exchange
    asset_class: AssetClass = AssetClass.equity
    instrument_type: InstrumentType = InstrumentType.eq
    isin: str | None = None
    nse_symbol: str | None = None
    bse_symbol: str | None = None
    sector: str | None = None
    industry: str | None = None
    lot_size: int = 1
    tick_size: float = 0.05
    currency: str = "INR"
    listing_date: date | None = None

    # --- lifecycle, carried from the discovery source ---------------------
    # Discovery is the authority on whether an instrument is still tradable, so
    # reconciliation can retire instruments that vanish from the exchange list.
    is_active: bool = True
    is_delisted: bool = False
    #: Discovery source that produced this row (e.g. "nse_equity"), for provenance.
    source: str | None = None
    #: Exchange-native identifier when the symbol is not the primary key
    #: (BSE scrip code, contract token, ...). Kept generic for future asset classes.
    exchange_token: str | None = None

    @field_validator("isin", mode="before")
    @classmethod
    def _normalize_isin(cls, v: str | None) -> str | None:
        """Reject placeholder and malformed ISINs instead of storing them.

        Exchange feeds use sentinel strings — BSE publishes the literal ``"NA"``
        for over a thousand scrips, and occasionally ``"0"`` or a truncated code.
        Stored verbatim these become fake identities: every ``"NA"`` row collides
        with every other, and cross-exchange mapping links unrelated companies.
        An ISIN we cannot trust is worth strictly less than no ISIN at all.
        """
        if v is None:
            return None
        candidate = str(v).strip().upper()
        if not candidate or candidate in _ISIN_SENTINELS:
            return None
        return candidate if _ISIN_PATTERN.match(candidate) else None


class OHLCVBar(BaseModel):
    """A single normalized candle. Timestamps must be timezone-aware (UTC-normalized)."""
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None

    @field_validator("ts")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("bar timestamp must be timezone-aware")
        return v


class OHLCVResponse(BaseModel):
    instrument_symbol: str
    exchange: Exchange
    timeframe: Timeframe
    bars: list[OHLCVBar]
    provider: str
    #: Corporate-action types the provider has *already* applied to these bars.
    #: The service must not re-apply these — doing so double-adjusts the series.
    #: Yahoo, for example, back-adjusts splits and bonuses into its Close, so a
    #: naive second adjustment halves every pre-split price a second time.
    pre_adjusted: frozenset[CorporateActionType] = frozenset()


class CorporateActionDTO(BaseModel):
    action_type: CorporateActionType
    ex_date: date
    record_date: date | None = None
    ratio_from: float | None = None
    ratio_to: float | None = None
    amount: float | None = None
    new_symbol: str | None = None
    details: dict | None = None


class ProviderHealth(BaseModel):
    provider: str
    status: ProviderStatus
    latency_ms: float | None = None
    detail: str | None = None
    checked_at: datetime
