"""Market data domain models: the Instrument Master, OHLCV hypertable, the
Corporate Action engine's records, the Market Calendar, and a quarantine table
for data that fails quality validation."""
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk
from app.domains.market_data.enums import (
    AssetClass,
    CorporateActionType,
    Exchange,
    InstrumentType,
    MarketCapCategory,
    QuarantineReason,
    SessionType,
    Timeframe,
)


class Instrument(UUIDPk, Timestamps, Base):
    """Instrument Master — single source of truth for every tradable instrument.

    Keyed by internal UUID; ISIN + trading symbol are the natural keys. Holds both
    NSE and BSE symbols since the same company lists on both under different tickers.
    """
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("trading_symbol", "exchange", name="uq_trading_symbol_exchange"),
    )

    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    nse_symbol: Mapped[str | None] = mapped_column(String(50), index=True)
    bse_symbol: Mapped[str | None] = mapped_column(String(50), index=True)
    trading_symbol: Mapped[str] = mapped_column(String(50), index=True)   # canonical ticker
    name: Mapped[str] = mapped_column(String(255))                        # company name

    # Exchange-native identifier where the ticker is not the exchange's own key:
    # BSE's numeric scrip code today, contract tokens for derivatives later. Some
    # vendors address BSE instruments by this code rather than the ticker, so it
    # must survive discovery rather than being dropped on the floor.
    exchange_token: Mapped[str | None] = mapped_column(String(32), index=True)

    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange), index=True)  # primary listing
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), default=AssetClass.equity)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType), default=InstrumentType.eq
    )

    sector: Mapped[str | None] = mapped_column(String(120), index=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    market_cap_category: Mapped[MarketCapCategory] = mapped_column(
        Enum(MarketCapCategory), default=MarketCapCategory.unknown
    )

    lot_size: Mapped[int] = mapped_column(default=1)
    tick_size: Mapped[float] = mapped_column(Numeric(10, 4), default=0.05)
    currency: Mapped[str] = mapped_column(String(3), default="INR")

    listing_date: Mapped[date | None] = mapped_column(Date)
    is_delisted: Mapped[bool] = mapped_column(default=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    # created_at / updated_at (last-updated) provided by Timestamps mixin.


class OHLCV(Base):
    """Time-series bars across all supported timeframes. TimescaleDB hypertable.

    Composite PK (instrument_id, timeframe, ts): the timeframe is part of the key,
    so the same instrument stores 1m…1mo bars side by side (multi-timeframe from day one).
    """
    __tablename__ = "ohlcv"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), primary_key=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(Enum(Timeframe), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    open: Mapped[float] = mapped_column(Numeric(18, 4))
    high: Mapped[float] = mapped_column(Numeric(18, 4))
    low: Mapped[float] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4))
    adjusted_close: Mapped[float | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int] = mapped_column(default=0)
    provider: Mapped[str | None] = mapped_column(String(40))   # provenance for auditing


class CorporateAction(UUIDPk, Timestamps, Base):
    """Corporate Action engine records. Drives price adjustment so historical data
    and backtests stay consistent across splits, bonuses, mergers, symbol changes, etc."""
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "action_type", "ex_date", name="uq_corp_action"
        ),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), index=True)
    action_type: Mapped[CorporateActionType] = mapped_column(
        Enum(CorporateActionType), index=True
    )
    ex_date: Mapped[date] = mapped_column(Date, index=True)
    record_date: Mapped[date | None] = mapped_column(Date)

    # Split/bonus expressed as ratio_from:ratio_to (e.g. 1:2 split -> from=1, to=2).
    ratio_from: Mapped[float | None] = mapped_column(Numeric(18, 6))
    ratio_to: Mapped[float | None] = mapped_column(Numeric(18, 6))
    amount: Mapped[float | None] = mapped_column(Numeric(18, 4))   # dividend / buyback price

    new_symbol: Mapped[str | None] = mapped_column(String(50))     # symbol_change / merger
    details: Mapped[dict | None] = mapped_column(JSON)             # action-specific extras
    is_applied: Mapped[bool] = mapped_column(default=False)        # adjustment applied flag


class MarketCalendar(UUIDPk, Timestamps, Base):
    """Trading calendar per exchange. No scheduler hardcodes dates — they read here.

    A row exists for every notable date: holidays, half-days, muhurat and special
    sessions, and unexpected closures. Normal-day trading hours are stored too so
    intraday syncs know the session window.
    """
    __tablename__ = "market_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "calendar_date", name="uq_calendar_exchange_date"),
    )

    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange), index=True)
    calendar_date: Mapped[date] = mapped_column(Date, index=True)
    session_type: Mapped[SessionType] = mapped_column(Enum(SessionType))
    open_time: Mapped[time | None] = mapped_column(Time)    # null for full holidays
    close_time: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    description: Mapped[str | None] = mapped_column(String(255))


class QuarantinedData(UUIDPk, Base):
    """Records rejected by data-quality validation. Nothing corrupt reaches ohlcv;
    it lands here with the raw payload for inspection and reprocessing."""
    __tablename__ = "quarantined_data"

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instruments.id"))
    provider: Mapped[str | None] = mapped_column(String(40))
    timeframe: Mapped[Timeframe | None] = mapped_column(Enum(Timeframe))
    reason: Mapped[QuarantineReason] = mapped_column(Enum(QuarantineReason), index=True)
    detail: Mapped[str | None] = mapped_column(String(500))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    # func.now() renders per dialect; a literal text("now()") is Postgres-only and
    # breaks the moment this table is exercised anywhere else.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
