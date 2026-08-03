"""Universe discovery: merging, ISIN hygiene, cross-mapping, and reconciliation.

Sources are stubbed. What is under test is the logic that turns several
disagreeing exchange feeds into one trustworthy Instrument Master — which is
where the damage happens if it is wrong.
"""
from datetime import date

import pytest

from app.domains.market_data.discovery.base import InstrumentSource, SourceResult
from app.domains.market_data.discovery.service import InstrumentUniverseService
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType
from app.domains.market_data.models import Instrument
from app.domains.market_data.schemas import InstrumentDTO


def dto(symbol: str, exchange: Exchange, isin: str | None = None, **kw) -> InstrumentDTO:  # noqa: ANN003
    return InstrumentDTO(
        trading_symbol=symbol, name=kw.pop("name", symbol), exchange=exchange,
        isin=isin, source=kw.pop("source", "stub"), **kw,
    )


class StubSource(InstrumentSource):
    def __init__(self, name: str, exchange: Exchange, instruments: list[InstrumentDTO],
                 asset_class: AssetClass = AssetClass.equity, error: Exception | None = None):
        self.name = name
        self.exchange = exchange
        self.asset_class = asset_class
        self._instruments = instruments
        self._error = error

    def fetch(self) -> list[InstrumentDTO]:
        if self._error:
            raise self._error
        return self._instruments


def service(sources: list[InstrumentSource], db=None) -> InstrumentUniverseService:  # noqa: ANN001
    return InstrumentUniverseService(db=db, sources=sources)


# --- ISIN hygiene --------------------------------------------------------
@pytest.mark.parametrize("raw", ["NA", "N/A", "NIL", "0", "-", "", "   ", "INE546A1014"])
def test_placeholder_and_malformed_isins_become_null(raw: str) -> None:
    """A sentinel stored as an ISIN is a fake identity that collides with every
    other sentinel — strictly worse than no ISIN."""
    assert dto("X", Exchange.BSE, isin=raw).isin is None


def test_valid_isin_is_preserved_and_upcased() -> None:
    assert dto("X", Exchange.NSE, isin="ine002a01018").isin == "INE002A01018"


def test_sentinel_isins_do_not_form_duplicate_groups() -> None:
    sources = [StubSource("bse", Exchange.BSE, [
        dto("AAA", Exchange.BSE, isin="NA"),
        dto("BBB", Exchange.BSE, isin="NA"),
        dto("CCC", Exchange.BSE, isin="NA"),
    ])]
    report = service(sources).discover()
    assert report.duplicates == []


# --- merging -------------------------------------------------------------
def test_active_listing_wins_over_retired_duplicate() -> None:
    """BSE publishes the same ticker across status buckets when a symbol is
    reused; the live row must survive the merge."""
    sources = [StubSource("bse", Exchange.BSE, [
        dto("REUSED", Exchange.BSE, isin="INE111A01011",
            is_active=False, is_delisted=True, name="Old Corp"),
        dto("REUSED", Exchange.BSE, isin="INE222A01012",
            is_active=True, name="New Corp"),
    ])]
    report = service(sources).discover()
    assert len(report.instruments) == 1
    survivor = report.instruments[0]
    assert survivor.is_active is True
    assert survivor.name == "New Corp"


def test_one_failing_source_does_not_discard_the_others() -> None:
    sources = [
        StubSource("broken", Exchange.NSE, [], error=RuntimeError("feed down")),
        StubSource("bse", Exchange.BSE, [dto("ABB", Exchange.BSE, isin="INE117A01022")]),
    ]
    report = service(sources).discover()
    assert len(report.instruments) == 1
    assert [r.source for r in report.failed_sources] == ["broken"]
    assert Exchange.NSE not in report.healthy_exchanges
    assert Exchange.BSE in report.healthy_exchanges


# --- cross-mapping -------------------------------------------------------
def test_dual_listed_company_is_cross_mapped_both_ways() -> None:
    sources = [
        StubSource("nse", Exchange.NSE, [dto("RELIANCE", Exchange.NSE, isin="INE002A01018")]),
        StubSource("bse", Exchange.BSE, [dto("RELIANCE", Exchange.BSE, isin="INE002A01018")]),
    ]
    report = service(sources).discover()
    assert report.cross_mapped == 1
    for instrument in report.instruments:
        assert instrument.nse_symbol == "RELIANCE"
        assert instrument.bse_symbol == "RELIANCE"


def test_retired_counter_sharing_an_isin_is_not_cross_mapped() -> None:
    """A delisted buyback counter carries the live company's ISIN.

    Mapping it would overwrite the dead row's identity with the live ticker and
    make the choice of "the" BSE symbol depend on iteration order.
    """
    sources = [
        StubSource("nse", Exchange.NSE, [dto("RELIANCE", Exchange.NSE, isin="INE002A01018")]),
        StubSource("bse", Exchange.BSE, [
            dto("RELIANCE", Exchange.BSE, isin="INE002A01018"),
            dto("RILBBPH", Exchange.BSE, isin="INE002A01018",
                is_active=False, is_delisted=True),
        ]),
    ]
    report = service(sources).discover()
    retired = next(i for i in report.instruments if i.trading_symbol == "RILBBPH")
    assert retired.nse_symbol is None, "a dead counter must not inherit the live ticker"
    assert retired.bse_symbol is None
    assert report.cross_mapped == 1

    live = next(
        i for i in report.instruments
        if i.trading_symbol == "RELIANCE" and i.exchange is Exchange.BSE
    )
    assert (live.nse_symbol, live.bse_symbol) == ("RELIANCE", "RELIANCE")


def test_ambiguous_isin_is_reported_instead_of_guessed() -> None:
    sources = [
        StubSource("nse", Exchange.NSE, [
            dto("AAA", Exchange.NSE, isin="INE002A01018"),
            dto("BBB", Exchange.NSE, isin="INE002A01018"),
        ]),
        StubSource("bse", Exchange.BSE, [dto("CCC", Exchange.BSE, isin="INE002A01018")]),
    ]
    report = service(sources).discover()
    assert report.cross_mapped == 0
    kinds = {d.kind for d in report.duplicates}
    assert "isin_ambiguous_mapping" in kinds


# --- reconciliation ------------------------------------------------------
def test_reconcile_creates_then_leaves_unchanged(db) -> None:  # noqa: ANN001
    sources = [StubSource("nse", Exchange.NSE, [
        dto("TCS", Exchange.NSE, isin="INE467B01029", name="Tata Consultancy",
            listing_date=date(2004, 8, 25)),
    ])]
    svc = service(sources, db=db)
    report = svc.discover()

    first = svc.reconcile(report)
    assert (first.created, first.updated, first.unchanged) == (1, 0, 0)

    second = svc.reconcile(svc.discover())
    assert (second.created, second.updated, second.unchanged) == (0, 0, 1)


def test_instrument_absent_from_a_healthy_feed_is_deactivated(db) -> None:  # noqa: ANN001
    svc = service([StubSource("nse", Exchange.NSE, [
        dto("GONE", Exchange.NSE, isin="INE111A01011"),
        dto("STAYS", Exchange.NSE, isin="INE222A01012"),
    ])], db=db)
    svc.reconcile(svc.discover())

    shrunk = service([StubSource("nse", Exchange.NSE, [
        dto("STAYS", Exchange.NSE, isin="INE222A01012"),
    ])], db=db)
    outcome = shrunk.reconcile(shrunk.discover())
    assert outcome.deactivated == 1

    rows = {i.trading_symbol: i for i in db.query(Instrument).all()}
    assert rows["GONE"].is_active is False
    assert rows["STAYS"].is_active is True


def test_a_failed_feed_never_retires_the_market(db) -> None:  # noqa: ANN001
    """The critical safety property: an outage must not read as mass delisting."""
    svc = service([StubSource("nse", Exchange.NSE, [
        dto("TCS", Exchange.NSE, isin="INE467B01029"),
        dto("INFY", Exchange.NSE, isin="INE009A01021"),
    ])], db=db)
    svc.reconcile(svc.discover())

    broken = service(
        [StubSource("nse", Exchange.NSE, [], error=RuntimeError("feed down"))], db=db
    )
    outcome = broken.reconcile(broken.discover())

    assert outcome.deactivated == 0
    assert all(i.is_active for i in db.query(Instrument).all())


def test_reconcile_does_not_blank_known_fields_with_empty_ones(db) -> None:  # noqa: ANN001
    """Sources differ in richness; a sparse feed must not erase a richer one."""
    rich = service([StubSource("nse", Exchange.NSE, [
        dto("TCS", Exchange.NSE, isin="INE467B01029", industry="IT Services"),
    ])], db=db)
    rich.reconcile(rich.discover())

    sparse = service([StubSource("nse", Exchange.NSE, [
        dto("TCS", Exchange.NSE, isin=None, industry=None),
    ])], db=db)
    sparse.reconcile(sparse.discover())

    row = db.query(Instrument).filter_by(trading_symbol="TCS").one()
    assert row.isin == "INE467B01029"
    assert row.industry == "IT Services"


def test_exchange_token_survives_into_the_master(db) -> None:  # noqa: ANN001
    """BSE's numeric scrip code is how several vendors address the instrument."""
    svc = service([StubSource("bse", Exchange.BSE, [
        dto("ABB", Exchange.BSE, isin="INE117A01022", exchange_token="500002"),
    ])], db=db)
    svc.reconcile(svc.discover())
    assert db.query(Instrument).one().exchange_token == "500002"


def test_source_failure_is_captured_not_raised() -> None:
    result = StubSource("x", Exchange.NSE, [], error=RuntimeError("boom")).collect()
    assert isinstance(result, SourceResult)
    assert result.ok is False
    assert "boom" in result.error


def test_asset_classes_and_exchanges_are_counted_for_reporting() -> None:
    sources = [
        StubSource("nse_eq", Exchange.NSE, [dto("TCS", Exchange.NSE, isin="INE467B01029")]),
        StubSource("nse_etf", Exchange.NSE, [
            dto("NIFTYBEES", Exchange.NSE, isin="INF204KB14I2",
                asset_class=AssetClass.etf, instrument_type=InstrumentType.etf),
        ], asset_class=AssetClass.etf),
    ]
    summary = service(sources).discover().summary()
    assert summary["by_asset_class"] == {"equity": 1, "etf": 1}
    assert summary["by_exchange"] == {"NSE": 2}
