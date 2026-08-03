"""Instrument Master validation and persistence semantics."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.domains.market_data.enums import (
    AssetClass,
    Exchange,
    InstrumentType,
    MarketCapCategory,
)
from app.domains.market_data.models import Instrument
from app.domains.market_data.schemas import InstrumentDTO


def test_dto_requires_core_identity_fields() -> None:
    with pytest.raises(ValidationError):
        InstrumentDTO(name="Missing symbol", exchange=Exchange.NSE)  # type: ignore[call-arg]


def test_dto_defaults_are_india_equity_sane() -> None:
    dto = InstrumentDTO(trading_symbol="TCS", name="TCS Ltd", exchange=Exchange.NSE)
    assert dto.asset_class is AssetClass.equity
    assert dto.instrument_type is InstrumentType.eq
    assert dto.currency == "INR"
    assert dto.lot_size == 1


def test_instrument_master_persists_full_identity(db) -> None:  # noqa: ANN001
    instrument = Instrument(
        trading_symbol="RELIANCE", name="Reliance Industries Ltd",
        exchange=Exchange.NSE, isin="INE002A01018",
        nse_symbol="RELIANCE", bse_symbol="500325",
        sector="Energy", industry="Refineries",
        market_cap_category=MarketCapCategory.large,
        lot_size=1, tick_size=0.05, currency="INR",
        listing_date=date(1977, 11, 1),
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)

    assert instrument.id is not None
    assert instrument.isin == "INE002A01018"
    assert instrument.nse_symbol == "RELIANCE"
    assert instrument.bse_symbol == "500325"
    assert instrument.market_cap_category is MarketCapCategory.large
    assert instrument.is_active is True
    assert instrument.is_delisted is False
    assert instrument.created_at is not None
    assert instrument.updated_at is not None


def test_dual_listing_uses_separate_rows_per_exchange(db) -> None:  # noqa: ANN001
    for exchange in (Exchange.NSE, Exchange.BSE):
        db.add(Instrument(
            trading_symbol="RELIANCE", name="Reliance Industries Ltd",
            exchange=exchange, isin="INE002A01018",
        ))
    db.commit()
    rows = db.query(Instrument).filter(Instrument.isin == "INE002A01018").all()
    assert len(rows) == 2, "same ISIN may list on both NSE and BSE"


def test_delisted_instrument_flagged(db) -> None:  # noqa: ANN001
    instrument = Instrument(
        trading_symbol="GONE", name="Delisted Co", exchange=Exchange.NSE,
        is_delisted=True, is_active=False,
    )
    db.add(instrument)
    db.commit()
    assert instrument.is_delisted is True
    assert instrument.is_active is False


def test_non_equity_asset_classes_supported(db) -> None:  # noqa: ANN001
    """Future asset classes must persist without schema changes."""
    for asset_class, itype in (
        (AssetClass.etf, InstrumentType.etf),
        (AssetClass.future, InstrumentType.futures),
        (AssetClass.option, InstrumentType.options),
        (AssetClass.crypto, InstrumentType.crypto),
        (AssetClass.forex, InstrumentType.currency),
        (AssetClass.commodity, InstrumentType.commodity),
    ):
        db.add(Instrument(
            trading_symbol=f"SYM_{asset_class.value}", name=f"{asset_class.value} instrument",
            exchange=Exchange.NSE, asset_class=asset_class, instrument_type=itype,
        ))
    db.commit()
    assert db.query(Instrument).count() == 6
