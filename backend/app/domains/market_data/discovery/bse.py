"""BSE instrument universe source.

BSE publishes its scrip master by lifecycle status, which is exactly what
reconciliation needs: delisted and suspended scrips are fetched deliberately
rather than inferred from absence.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.domains.market_data.discovery.base import DiscoveryError, InstrumentSource
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType
from app.domains.market_data.schemas import InstrumentDTO

log = get_logger(__name__)

BSE_HOME = "https://www.bseindia.com/"
SCRIP_LIST_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
    "?Group=&Scripcode=&industry=&segment={segment}&status={status}"
)

#: Lifecycle buckets BSE exposes. Fetching all three is what makes delisting
#: detection authoritative instead of a guess based on a missing row.
STATUSES = ("Active", "Delisted", "Suspended")


class BSEEquitySource(InstrumentSource):
    """Every BSE equity scrip across active, suspended, and delisted states.

    ``trading_symbol`` is BSE's ``scrip_id`` (the human ticker) while the numeric
    ``SCRIP_CD`` is preserved as ``exchange_token`` — several data vendors,
    Yahoo included, key BSE instruments by the numeric code, so losing it would
    make downstream symbol mapping impossible.
    """

    name = "bse_equity"
    exchange = Exchange.BSE
    asset_class = AssetClass.equity
    segment = "Equity"

    def fetch(self) -> list[InstrumentDTO]:
        self._client.warm(BSE_HOME)
        instruments: list[InstrumentDTO] = []
        failures: list[str] = []

        for status in STATUSES:
            url = SCRIP_LIST_URL.format(segment=self.segment, status=status)
            try:
                rows = self._client.get_json(url, referer=BSE_HOME)
            except DiscoveryError as exc:
                # A missing lifecycle bucket degrades reconciliation but must not
                # discard the buckets that did load.
                failures.append(f"{status}: {exc}")
                log.warning("bse_status_fetch_failed", status=status, error=str(exc))
                continue
            if not isinstance(rows, list):
                failures.append(f"{status}: unexpected payload type {type(rows).__name__}")
                continue
            instruments.extend(self._to_dtos(rows, status))

        if not instruments:
            raise DiscoveryError(f"BSE scrip list produced nothing ({'; '.join(failures)})")
        if failures:
            log.warning("bse_partial_discovery", failures=failures, count=len(instruments))
        return instruments

    def _to_dtos(self, rows: list[dict], status: str) -> list[InstrumentDTO]:
        delisted = status == "Delisted"
        active = status == "Active"
        out: list[InstrumentDTO] = []
        for row in rows:
            scrip_code = str(row.get("SCRIP_CD") or "").strip()
            symbol = str(row.get("scrip_id") or "").strip().upper()
            # Some scrips (mostly debt-like or very old rows) carry no ticker;
            # fall back to the numeric code so the row stays addressable.
            if not symbol:
                symbol = scrip_code
            if not symbol:
                continue
            industry = (row.get("INDUSTRY") or "").strip() or None
            out.append(InstrumentDTO(
                trading_symbol=symbol,
                bse_symbol=symbol,
                exchange_token=scrip_code or None,
                name=(row.get("Scrip_Name") or row.get("Issuer_Name") or symbol).strip(),
                exchange=Exchange.BSE,
                asset_class=AssetClass.equity,
                instrument_type=InstrumentType.eq,
                isin=(row.get("ISIN_NUMBER") or "").strip() or None,
                industry=industry,
                currency="INR",
                is_active=active,
                is_delisted=delisted,
                source=self.name,
            ))
        return out
