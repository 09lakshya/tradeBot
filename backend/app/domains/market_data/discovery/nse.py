"""NSE instrument universe sources: equities, ETFs, and indices.

All three read NSE's own published lists, so the Instrument Master is seeded from
the exchange rather than from a hand-maintained symbol list.
"""
from __future__ import annotations

from datetime import date, datetime

from app.core.logging import get_logger
from app.domains.market_data.discovery.base import DiscoveryError, InstrumentSource
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType
from app.domains.market_data.schemas import InstrumentDTO

log = get_logger(__name__)

NSE_HOME = "https://www.nseindia.com/"
_ARCHIVES = "https://nsearchives.nseindia.com/content/equities"

EQUITY_LIST_URL = f"{_ARCHIVES}/EQUITY_L.csv"
ETF_LIST_URL = f"{_ARCHIVES}/eq_etfseclist.csv"
INDICES_URL = "https://www.nseindia.com/api/allIndices"

#: NSE equity series still open for trading. EQ = rolling settlement,
#: BE/BZ = trade-for-trade (restricted, but tradable and therefore in-universe).
TRADABLE_SERIES = {"EQ", "BE", "BZ"}


def _parse_date(raw: str) -> date | None:
    """NSE publishes listing dates in several formats across its own files."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    log.debug("nse_unparsed_listing_date", value=raw)
    return None


def _parse_int(raw: str, default: int = 1) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


class NSEEquitySource(InstrumentSource):
    """Every equity listed on NSE, from the official ``EQUITY_L.csv``."""

    name = "nse_equity"
    exchange = Exchange.NSE
    asset_class = AssetClass.equity

    def fetch(self) -> list[InstrumentDTO]:
        self._client.warm(NSE_HOME)
        rows = self._client.get_csv(
            EQUITY_LIST_URL,
            referer=f"{NSE_HOME}market-data/securities-available-for-trading",
        )
        if not rows:
            raise DiscoveryError("NSE equity list returned zero rows")

        instruments: list[InstrumentDTO] = []
        for row in rows:
            symbol = row.get("SYMBOL", "").strip().upper()
            if not symbol:
                continue
            series = row.get("SERIES", "").strip().upper()
            isin = row.get("ISIN NUMBER", "").strip() or None
            instruments.append(InstrumentDTO(
                trading_symbol=symbol,
                nse_symbol=symbol,
                name=row.get("NAME OF COMPANY", "").strip() or symbol,
                exchange=Exchange.NSE,
                asset_class=AssetClass.equity,
                instrument_type=InstrumentType.eq,
                isin=isin,
                lot_size=_parse_int(row.get("MARKET LOT", "1")),
                listing_date=_parse_date(row.get("DATE OF LISTING", "")),
                currency="INR",
                # Presence in EQUITY_L.csv *is* the exchange asserting the symbol
                # is live; anything retired drops out of the file entirely.
                is_active=series in TRADABLE_SERIES,
                is_delisted=False,
                source=self.name,
            ))
        return instruments


class NSEEtfSource(InstrumentSource):
    """Every ETF listed on NSE, from the official ETF security list."""

    name = "nse_etf"
    exchange = Exchange.NSE
    asset_class = AssetClass.etf

    def fetch(self) -> list[InstrumentDTO]:
        self._client.warm(NSE_HOME)
        rows = self._client.get_csv(
            ETF_LIST_URL, referer=f"{NSE_HOME}market-data/exchange-traded-funds-etf"
        )
        if not rows:
            raise DiscoveryError("NSE ETF list returned zero rows")

        instruments: list[InstrumentDTO] = []
        for row in rows:
            symbol = row.get("Symbol", "").strip().upper()
            if not symbol:
                continue
            instruments.append(InstrumentDTO(
                trading_symbol=symbol,
                nse_symbol=symbol,
                # SecurityName is the compressed exchange name; Underlying is the
                # human-meaningful descriptor, so prefer it and fall back.
                name=(row.get("SecurityName") or row.get("Underlying") or symbol).strip(),
                exchange=Exchange.NSE,
                asset_class=AssetClass.etf,
                instrument_type=InstrumentType.etf,
                isin=row.get("ISINNumber", "").strip() or None,
                lot_size=_parse_int(row.get("MarketLot", "1")),
                listing_date=_parse_date(row.get("DateofListing", "")),
                currency="INR",
                source=self.name,
            ))
        return instruments


class NSEIndexSource(InstrumentSource):
    """Every index NSE publishes, from the live index snapshot endpoint.

    Indices have no ISIN and are not directly tradable, but they are first-class
    instruments for strategy signals and benchmarking, so they belong in the master.
    """

    name = "nse_index"
    exchange = Exchange.NSE
    asset_class = AssetClass.index

    def fetch(self) -> list[InstrumentDTO]:
        self._client.warm(NSE_HOME)
        payload = self._client.get_json(
            INDICES_URL, referer=f"{NSE_HOME}market-data/live-market-indices"
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not rows:
            raise DiscoveryError("NSE indices endpoint returned no data")

        instruments: list[InstrumentDTO] = []
        for row in rows:
            symbol = (row.get("indexSymbol") or row.get("index") or "").strip().upper()
            if not symbol:
                continue
            instruments.append(InstrumentDTO(
                trading_symbol=symbol,
                nse_symbol=symbol,
                name=(row.get("index") or symbol).strip(),
                exchange=Exchange.NSE,
                asset_class=AssetClass.index,
                instrument_type=InstrumentType.index,
                isin=None,
                lot_size=1,
                currency="INR",
                source=self.name,
            ))
        return instruments
