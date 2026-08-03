"""Discovery source parsers, driven by a stubbed HTTP client (no network).

These lock the mapping from each exchange's real payload shape — captured from
live responses — onto our DTOs, including the quirks that bit us live: stray
header spaces, sentinel ISINs, and BSE's status buckets.
"""
from app.domains.market_data.discovery.bse import BSEEquitySource
from app.domains.market_data.discovery.calendars import NSEHolidaySource
from app.domains.market_data.discovery.nse import (
    NSEEquitySource,
    NSEEtfSource,
    NSEIndexSource,
)
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType, SessionType


class FakeClient:
    """Stub returning canned payloads keyed by URL substring."""

    def __init__(self, csv=None, json=None):  # noqa: ANN001
        self._csv = csv or {}
        self._json = json or {}

    def warm(self, url):  # noqa: ANN001, ANN202
        pass

    def get_csv(self, url, referer=None):  # noqa: ANN001, ANN202
        for key, rows in self._csv.items():
            if key in url:
                return rows
        raise AssertionError(f"unexpected csv url {url}")

    def get_json(self, url, referer=None):  # noqa: ANN001, ANN202
        for key, payload in self._json.items():
            if key in url:
                return payload
        raise AssertionError(f"unexpected json url {url}")


# --- NSE equity ----------------------------------------------------------
def test_nse_equity_parses_official_csv_shape() -> None:
    rows = [
        {"SYMBOL": "20MICRONS", "NAME OF COMPANY": "20 Microns Limited",
         "SERIES": "EQ", "DATE OF LISTING": "06-OCT-2008", "MARKET LOT": "1",
         "ISIN NUMBER": "INE144J01027", "FACE VALUE": "5"},
        {"SYMBOL": "SOMEBOND", "NAME OF COMPANY": "Some Bond",
         "SERIES": "GB", "DATE OF LISTING": "01-JAN-2020", "MARKET LOT": "1",
         "ISIN NUMBER": "INE000000000", "FACE VALUE": "100"},
    ]
    source = NSEEquitySource(FakeClient(csv={"EQUITY_L": rows}))
    out = {i.trading_symbol: i for i in source.fetch()}

    eq = out["20MICRONS"]
    assert eq.exchange is Exchange.NSE
    assert eq.asset_class is AssetClass.equity
    assert eq.instrument_type is InstrumentType.eq
    assert eq.isin == "INE144J01027"
    assert eq.nse_symbol == "20MICRONS"
    assert eq.is_active is True
    assert eq.listing_date is not None
    # A non-tradable series is discovered but flagged inactive, not dropped.
    assert out["SOMEBOND"].is_active is False


def test_nse_equity_empty_feed_raises() -> None:
    import pytest

    from app.domains.market_data.discovery.base import DiscoveryError
    source = NSEEquitySource(FakeClient(csv={"EQUITY_L": []}))
    with pytest.raises(DiscoveryError):
        source.fetch()


# --- NSE ETF -------------------------------------------------------------
def test_nse_etf_parses_and_types_as_etf() -> None:
    rows = [{"Symbol": "NIFTYBEES", "Underlying": "Nifty50",
             "SecurityName": "NIPINDETFNIFTYBEES", "DateofListing": "08-Jan-02",
             "MarketLot": "1", "ISINNumber": "INF204KB14I2", "FaceValue": "1"}]
    source = NSEEtfSource(FakeClient(csv={"etfseclist": rows}))
    etf = source.fetch()[0]
    assert etf.asset_class is AssetClass.etf
    assert etf.instrument_type is InstrumentType.etf
    assert etf.isin == "INF204KB14I2"


# --- NSE index -----------------------------------------------------------
def test_nse_index_parses_snapshot_and_has_no_isin() -> None:
    payload = {"data": [
        {"key": "BROAD", "index": "NIFTY 50", "indexSymbol": "NIFTY 50", "last": 1.0},
        {"key": "BROAD", "index": "NIFTY BANK", "indexSymbol": "NIFTY BANK", "last": 2.0},
    ]}
    source = NSEIndexSource(FakeClient(json={"allIndices": payload}))
    out = source.fetch()
    assert {i.trading_symbol for i in out} == {"NIFTY 50", "NIFTY BANK"}
    assert all(i.asset_class is AssetClass.index for i in out)
    assert all(i.isin is None for i in out)


# --- BSE equity ----------------------------------------------------------
def _bse_row(scrip_id, code, isin, status="Active", name="Co"):  # noqa: ANN001, ANN202
    return {"SCRIP_CD": code, "scrip_id": scrip_id, "ISIN_NUMBER": isin,
            "Scrip_Name": name, "Status": status, "INDUSTRY": "Widgets"}


def test_bse_fetches_all_status_buckets_and_flags_lifecycle() -> None:
    payloads = {
        "status=Active": [_bse_row("ABB", "500002", "INE117A01022")],
        "status=Delisted": [_bse_row("OLDCO", "500003", "INE111A01011", "Delisted")],
        "status=Suspended": [_bse_row("SUSP", "500004", "INE222A01012", "Suspended")],
    }
    source = BSEEquitySource(FakeClient(json=payloads))
    out = {i.trading_symbol: i for i in source.fetch()}

    assert out["ABB"].is_active is True and out["ABB"].is_delisted is False
    assert out["ABB"].exchange_token == "500002"
    assert out["OLDCO"].is_delisted is True and out["OLDCO"].is_active is False
    assert out["SUSP"].is_active is False and out["SUSP"].is_delisted is False


def test_bse_sentinel_isin_is_normalized_away() -> None:
    payloads = {
        "status=Active": [_bse_row("NOISIN", "500005", "NA")],
        "status=Delisted": [], "status=Suspended": [],
    }
    source = BSEEquitySource(FakeClient(json=payloads))
    assert source.fetch()[0].isin is None


def test_bse_falls_back_to_scrip_code_when_ticker_missing() -> None:
    payloads = {
        "status=Active": [{"SCRIP_CD": "999999", "scrip_id": "", "ISIN_NUMBER": "",
                           "Scrip_Name": "No Ticker Co", "Status": "Active"}],
        "status=Delisted": [], "status=Suspended": [],
    }
    source = BSEEquitySource(FakeClient(json=payloads))
    out = source.fetch()[0]
    assert out.trading_symbol == "999999"
    assert out.exchange_token == "999999"


# --- NSE holidays --------------------------------------------------------
def test_nse_holiday_source_separates_closures_from_ceremonial_sessions() -> None:
    payload = {"CM": [
        {"tradingDate": "26-Jan-2026", "description": "Republic Day",
         "morning_session": None, "evening_session": None},
        {"tradingDate": "08-Nov-2026", "description": "Diwali Muhurat",
         "morning_session": "", "evening_session": "18:15-19:15"},
    ]}
    source = NSEHolidaySource(FakeClient(json={"holiday-master": payload}))
    out = {e.calendar_date.isoformat(): e for e in source.fetch()}

    assert out["2026-01-26"].session_type is SessionType.holiday
    # A holiday carrying a session window is a muhurat session — the market opens.
    assert out["2026-11-08"].session_type is SessionType.muhurat
    assert out["2026-11-08"].open_time is not None
