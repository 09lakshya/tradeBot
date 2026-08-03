"""Exchange trading-calendar sources.

The holiday list is reference data that changes every year and is amended
mid-year (election days, unscheduled closures). Hardcoding it guarantees drift,
and drift here is expensive in both directions: a phantom holiday quarantines
genuine bars, while a missing one lets the pipeline treat a closed day as a gap.
So the calendar is discovered from the exchange, exactly like the instrument
universe.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.logging import get_logger
from app.domains.market_data.discovery.base import (
    DiscoveryError,
    ExchangeHttpClient,
)
from app.domains.market_data.enums import Exchange, SessionType

log = get_logger(__name__)

NSE_HOME = "https://www.nseindia.com/"
HOLIDAY_MASTER_URL = f"{NSE_HOME}api/holiday-master?type=trading"

#: NSE's holiday master is segmented; "CM" is the cash/equity market.
EQUITY_SEGMENT = "CM"

_DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d")


@dataclass(frozen=True)
class CalendarEntry:
    calendar_date: date
    session_type: SessionType
    description: str
    open_time: time | None = None
    close_time: time | None = None


class HolidaySource(ABC):
    """Authority for one exchange's non-trading days and special sessions."""

    name: str = "base"
    exchange: Exchange

    def __init__(self, client: ExchangeHttpClient | None = None) -> None:
        self._client = client or ExchangeHttpClient()

    @abstractmethod
    def fetch(self) -> list[CalendarEntry]:
        """Return every published calendar exception for the covered period."""


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class NSEHolidaySource(HolidaySource):
    """NSE's published holiday master for the cash market.

    Note the coverage limit: the endpoint serves the *current* calendar year only.
    Callers must treat years outside the returned range as unknown rather than
    assuming they were normal trading years — see
    :meth:`MarketCalendarService.has_authoritative_coverage`.
    """

    name = "nse_holidays"
    exchange = Exchange.NSE

    def fetch(self) -> list[CalendarEntry]:
        self._client.warm(NSE_HOME)
        payload = self._client.get_json(
            HOLIDAY_MASTER_URL,
            referer=f"{NSE_HOME}resources/exchange-communication-holidays",
        )
        if not isinstance(payload, dict):
            raise DiscoveryError("NSE holiday master returned an unexpected payload")
        rows = payload.get(EQUITY_SEGMENT)
        if not rows:
            raise DiscoveryError(
                f"NSE holiday master has no {EQUITY_SEGMENT} segment "
                f"(got {sorted(payload)})"
            )

        entries: list[CalendarEntry] = []
        for row in rows:
            day = _parse_date(row.get("tradingDate") or row.get("holidayDate") or "")
            if day is None:
                log.warning("nse_holiday_unparsed_date", row=row)
                continue
            description = (row.get("description") or "").strip()
            evening = (row.get("evening_session") or "").strip()
            morning = (row.get("morning_session") or "").strip()
            # A holiday that still carries a session window is a ceremonial
            # session (Diwali muhurat), not a closure — the market *is* open.
            if evening or morning:
                entries.append(CalendarEntry(
                    calendar_date=day, session_type=SessionType.muhurat,
                    description=description or "Special session",
                    open_time=time(18, 15), close_time=time(19, 15),
                ))
                continue
            entries.append(CalendarEntry(
                calendar_date=day, session_type=SessionType.holiday,
                description=description or "Exchange holiday",
            ))
        if not entries:
            raise DiscoveryError("NSE holiday master produced no usable entries")
        log.info("nse_holidays_fetched", count=len(entries))
        return entries


class BSEHolidaySource(NSEHolidaySource):
    """BSE observes the same equity-market holiday schedule as NSE.

    Modelled as its own source rather than assumed at the call site, so the day
    the two diverge only this class changes.
    """

    name = "bse_holidays"
    exchange = Exchange.BSE
