"""Market calendar: trading days, sessions, timezone handling, navigation."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.domains.market_data.calendar import IST, MarketCalendarService, seed_calendar
from app.domains.market_data.enums import Exchange, SessionType
from app.domains.market_data.models import MarketCalendar


def test_weekend_is_not_a_trading_day(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, date(2026, 1, 3)) is False   # Saturday
    assert cal.is_trading_day(Exchange.NSE, date(2026, 1, 4)) is False   # Sunday


def test_ordinary_weekday_is_a_trading_day(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, date(2026, 1, 6)) is True    # Tuesday


#: Calendar fixtures are declared by the test, not imported from a shipped list —
#: the real holiday set is discovered from the exchange and changes every year.
REPUBLIC_DAY = date(2026, 1, 26)
MUHURAT = date(2026, 11, 8)
ENTRIES = [
    (REPUBLIC_DAY, SessionType.holiday, "Republic Day"),
    (MUHURAT, SessionType.muhurat, "Muhurat Trading (Diwali)"),
]


def test_seeded_holiday_closes_the_market(db) -> None:  # noqa: ANN001
    seed_calendar(db, entries=ENTRIES)
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, REPUBLIC_DAY) is False
    assert cal.session_type(Exchange.NSE, REPUBLIC_DAY) is SessionType.holiday


def test_seed_is_idempotent(db) -> None:  # noqa: ANN001
    first = seed_calendar(db, entries=ENTRIES)
    second = seed_calendar(db, entries=ENTRIES)
    assert first > 0
    assert second == 0, "re-seeding must not duplicate rows"


def test_muhurat_session_is_a_trading_day_with_evening_hours(db) -> None:  # noqa: ANN001
    seed_calendar(db, entries=ENTRIES)
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, MUHURAT) is True
    hours = cal.trading_hours(Exchange.NSE, MUHURAT)
    assert hours == (time(18, 15), time(19, 15))


def test_half_day_uses_shortened_session(db) -> None:  # noqa: ANN001
    db.add(MarketCalendar(
        exchange=Exchange.NSE, calendar_date=date(2026, 2, 10),
        session_type=SessionType.half_day, open_time=time(9, 15),
        close_time=time(12, 30), description="Half day",
    ))
    db.commit()
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, date(2026, 2, 10)) is True
    assert cal.trading_hours(Exchange.NSE, date(2026, 2, 10)) == (time(9, 15), time(12, 30))


def test_unexpected_closure_blocks_trading(db) -> None:  # noqa: ANN001
    db.add(MarketCalendar(
        exchange=Exchange.NSE, calendar_date=date(2026, 3, 10),
        session_type=SessionType.unexpected_closure, description="Technical outage",
    ))
    db.commit()
    cal = MarketCalendarService(db)
    assert cal.is_trading_day(Exchange.NSE, date(2026, 3, 10)) is False


def test_default_hours_for_normal_day(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.trading_hours(Exchange.NSE, date(2026, 1, 6)) == (time(9, 15), time(15, 30))


def test_trading_hours_none_when_closed(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.trading_hours(Exchange.NSE, date(2026, 1, 4)) is None


def test_next_trading_day_skips_weekend(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    # Friday 2026-01-02 -> next is Monday 2026-01-05
    assert cal.next_trading_day(Exchange.NSE, date(2026, 1, 2)) == date(2026, 1, 5)


def test_previous_trading_day_skips_weekend(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.previous_trading_day(Exchange.NSE, date(2026, 1, 5)) == date(2026, 1, 2)


def test_trading_days_between_excludes_weekends(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    days = cal.trading_days_between(Exchange.NSE, date(2026, 1, 5), date(2026, 1, 11))
    assert days == [date(2026, 1, d) for d in (5, 6, 7, 8, 9)]


def test_is_market_open_respects_ist_session_window(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    trading_day = datetime(2026, 1, 6, 11, 0, tzinfo=IST)
    assert cal.is_market_open(Exchange.NSE, trading_day) is True

    after_close = datetime(2026, 1, 6, 16, 0, tzinfo=IST)
    assert cal.is_market_open(Exchange.NSE, after_close) is False


def test_is_market_open_converts_from_other_timezone(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    # 05:45 UTC == 11:15 IST -> market open
    utc_moment = datetime(2026, 1, 6, 5, 45, tzinfo=ZoneInfo("UTC"))
    assert cal.is_market_open(Exchange.NSE, utc_moment) is True


def test_is_market_open_false_on_weekend(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    assert cal.is_market_open(Exchange.NSE, datetime(2026, 1, 4, 11, 0, tzinfo=IST)) is False


def test_checker_binds_exchange_for_validator(db) -> None:  # noqa: ANN001
    cal = MarketCalendarService(db)
    checker = cal.is_trading_day_checker(Exchange.NSE)
    assert checker(date(2026, 1, 6)) is True
    assert checker(date(2026, 1, 4)) is False
