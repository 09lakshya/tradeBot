"""Market Calendar service — DB-backed trading calendar per exchange.

Schedulers and validators call this instead of hardcoding dates. Trading-day
resolution is: weekend -> closed; an explicit calendar row (holiday / unexpected
closure) -> closed; half-day / muhurat / special -> open with the stored session
window; otherwise a normal session with default hours.

The holiday set is *data*, loaded via :func:`seed_calendar` and refreshable from an
exchange feed — no scheduler ever embeds a date literal.
"""
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.market_data.cache import MarketCache
from app.domains.market_data.enums import Exchange, SessionType
from app.domains.market_data.models import MarketCalendar
from app.domains.market_data.sessions import IST, exchange_timezone

log = get_logger(__name__)

__all__ = [
    "DEFAULT_HOURS", "IST", "MarketCalendarService",
    "exchange_timezone", "seed_calendar", "sync_calendar",
]

#: Default equity session window when no explicit calendar row exists.
DEFAULT_HOURS: dict[Exchange, tuple[time, time]] = {
    Exchange.NSE: (time(9, 15), time(15, 30)),
    Exchange.BSE: (time(9, 15), time(15, 30)),
}

#: Session types that still permit trading.
_OPEN_SESSIONS = {SessionType.normal, SessionType.half_day, SessionType.muhurat,
                  SessionType.special}


class MarketCalendarService:
    """Trading-calendar queries. Cache-accelerated, DB-authoritative."""

    def __init__(
        self,
        db: Session,
        cache: MarketCache | None = None,
        timezone: ZoneInfo = IST,
    ) -> None:
        self._db = db
        self._cache = cache or MarketCache()
        self._tz = timezone

    # --- lookups --------------------------------------------------------
    def _entry(self, exchange: Exchange, day: date) -> MarketCalendar | None:
        stmt = select(MarketCalendar).where(
            MarketCalendar.exchange == exchange,
            MarketCalendar.calendar_date == day,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def session_type(self, exchange: Exchange, day: date) -> SessionType:
        entry = self._entry(exchange, day)
        if entry is not None:
            return entry.session_type
        if day.weekday() >= 5:  # Saturday/Sunday
            return SessionType.holiday
        return SessionType.normal

    def is_trading_day(self, exchange: Exchange, day: date) -> bool:
        cached = self._cache.get("calendar", exchange.value, day.isoformat())
        if cached is not None:
            return bool(cached)
        result = self.session_type(exchange, day) in _OPEN_SESSIONS
        self._cache.set("calendar", result, exchange.value, day.isoformat())
        return result

    def covered_years(self, exchange: Exchange) -> set[int]:
        """Years for which this exchange has loaded calendar rows."""
        rows = self._db.execute(
            select(MarketCalendar.calendar_date).where(MarketCalendar.exchange == exchange)
        ).scalars()
        return {d.year for d in rows}

    def has_authoritative_coverage(self, exchange: Exchange, day: date) -> bool:
        """True when the calendar can actually speak to this date.

        Exchange holiday feeds publish the current year only. Outside that range
        an absent row means "not loaded", not "normal trading day", and treating
        the two alike is how correct data gets thrown away.
        """
        return day.year in self.covered_years(exchange)

    def is_known_non_trading_day(self, exchange: Exchange, day: date) -> bool:
        """True only when the market is *provably* closed.

        Weekends are provable everywhere. A weekday closure is provable only where
        the calendar has authoritative coverage. Anything else returns False, so
        callers err toward keeping data rather than discarding it.
        """
        if day.weekday() >= 5:
            return True
        if not self.has_authoritative_coverage(exchange, day):
            return False
        return not self.is_trading_day(exchange, day)

    def trading_hours(self, exchange: Exchange, day: date) -> tuple[time, time] | None:
        """Session open/close for a day, or ``None`` if the market is closed."""
        if not self.is_trading_day(exchange, day):
            return None
        entry = self._entry(exchange, day)
        if entry is not None and entry.open_time and entry.close_time:
            return entry.open_time, entry.close_time
        return DEFAULT_HOURS.get(exchange, (time(9, 15), time(15, 30)))

    def is_market_open(self, exchange: Exchange, moment: datetime | None = None) -> bool:
        """Timezone-aware 'is the market open right now'."""
        moment = moment or datetime.now(self._tz)
        local = moment.astimezone(self._tz)
        hours = self.trading_hours(exchange, local.date())
        if hours is None:
            return False
        open_t, close_t = hours
        return open_t <= local.time() <= close_t

    # --- navigation -----------------------------------------------------
    def next_trading_day(self, exchange: Exchange, day: date, lookahead: int = 30) -> date | None:
        cursor = day + timedelta(days=1)
        for _ in range(lookahead):
            if self.is_trading_day(exchange, cursor):
                return cursor
            cursor += timedelta(days=1)
        return None

    def previous_trading_day(
        self, exchange: Exchange, day: date, lookback: int = 30
    ) -> date | None:
        cursor = day - timedelta(days=1)
        for _ in range(lookback):
            if self.is_trading_day(exchange, cursor):
                return cursor
            cursor -= timedelta(days=1)
        return None

    def trading_days_between(self, exchange: Exchange, start: date, end: date) -> list[date]:
        days: list[date] = []
        cursor = start
        while cursor <= end:
            if self.is_trading_day(exchange, cursor):
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def is_trading_day_checker(self, exchange: Exchange) -> Callable[[date], bool]:
        """Bind an exchange to produce the callable the validator expects."""
        return lambda d: self.is_trading_day(exchange, d)

    def known_closure_checker(self, exchange: Exchange) -> Callable[[date], bool]:
        """Checker for quarantine decisions: only provable closures reject a bar."""
        return lambda d: self.is_known_non_trading_day(exchange, d)


# --- loading ------------------------------------------------------------
def seed_calendar(
    db: Session,
    exchanges: tuple[Exchange, ...] = (Exchange.NSE, Exchange.BSE),
    entries: list[tuple[date, SessionType, str]] | None = None,
) -> int:
    """Idempotently insert explicit calendar rows. Returns the number created.

    This is the low-level loader used by tests and manual corrections. Production
    calendars come from :func:`sync_calendar`, which reads the exchange's own
    holiday master — a hardcoded holiday list is wrong within one amendment cycle,
    and a wrong calendar silently quarantines real bars.
    """
    if not entries:
        return 0
    created = 0
    for exchange in exchanges:
        for day, session, description in entries:
            exists = db.execute(
                select(MarketCalendar).where(
                    MarketCalendar.exchange == exchange,
                    MarketCalendar.calendar_date == day,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            open_t, close_t = (None, None)
            if session is SessionType.muhurat:
                open_t, close_t = time(18, 15), time(19, 15)
            elif session is SessionType.half_day:
                open_t, close_t = time(9, 15), time(12, 30)
            db.add(MarketCalendar(
                exchange=exchange, calendar_date=day, session_type=session,
                open_time=open_t, close_time=close_t, description=description,
            ))
            created += 1
    db.commit()
    log.info("calendar_seeded", created=created)
    return created


def sync_calendar(db: Session, sources: list[object] | None = None) -> dict[str, int]:
    """Refresh the trading calendar from each exchange's published holiday master.

    Rows are reconciled, not merely inserted: a date the exchange has *withdrawn*
    (an election holiday that got cancelled) must disappear, otherwise the stale
    row keeps rejecting good data forever. Reconciliation is scoped to the years
    the feed actually covers so untouched history is left alone.
    """
    from app.domains.market_data.discovery.calendars import (
        BSEHolidaySource,
        HolidaySource,
        NSEHolidaySource,
    )

    active: list[HolidaySource] = list(sources) if sources else [  # type: ignore[arg-type]
        NSEHolidaySource(), BSEHolidaySource(),
    ]
    totals = {"created": 0, "updated": 0, "removed": 0, "unchanged": 0, "failed": 0}

    for source in active:
        try:
            entries = source.fetch()
        except Exception as exc:  # noqa: BLE001 - one feed must not break the rest
            log.warning("calendar_sync_failed", source=source.name, error=str(exc))
            totals["failed"] += 1
            continue

        years = {e.calendar_date.year for e in entries}
        existing = {
            row.calendar_date: row
            for row in db.execute(
                select(MarketCalendar).where(MarketCalendar.exchange == source.exchange)
            ).scalars()
            if row.calendar_date.year in years
        }
        seen: set[date] = set()

        for entry in entries:
            seen.add(entry.calendar_date)
            row = existing.get(entry.calendar_date)
            if row is None:
                db.add(MarketCalendar(
                    exchange=source.exchange, calendar_date=entry.calendar_date,
                    session_type=entry.session_type, description=entry.description,
                    open_time=entry.open_time, close_time=entry.close_time,
                ))
                totals["created"] += 1
                continue
            if (row.session_type, row.description) != (entry.session_type, entry.description):
                row.session_type = entry.session_type
                row.description = entry.description
                row.open_time = entry.open_time
                row.close_time = entry.close_time
                totals["updated"] += 1
            else:
                totals["unchanged"] += 1

        for day, row in existing.items():
            if day not in seen:
                db.delete(row)
                totals["removed"] += 1

    db.commit()
    log.info("calendar_synced", **totals)
    return totals
