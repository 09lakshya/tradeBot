"""Live-validation harness: durable progress, batching, and the bar-level checks.

The resumability guarantee is the point of this module — a run that cannot be
interrupted safely is useless against a rate-limited provider — so it is tested
directly rather than inferred.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.market_data.calendar import MarketCalendarService, seed_calendar
from app.domains.market_data.enums import AssetClass, Exchange, SessionType, Timeframe
from app.domains.market_data.live_validation import (
    CRITICAL,
    WARNING,
    CheckpointStore,
    Finding,
    LiveMarketDataValidator,
    UnitResult,
    ValidationUnit,
    check_calendar_alignment,
    check_monotonic,
    check_price_sanity,
    check_session_alignment,
    check_synthetic_bars,
    check_timezone,
)
from app.domains.market_data.models import Instrument
from app.domains.market_data.schemas import OHLCVBar
from app.domains.market_data.sessions import IST


@pytest.fixture
def store(tmp_path) -> CheckpointStore:  # noqa: ANN001
    return CheckpointStore(tmp_path / "progress.sqlite")


def unit(symbol: str = "TCS", tf: Timeframe = Timeframe.d1) -> ValidationUnit:
    return ValidationUnit(symbol, Exchange.NSE, tf)


def result(u: ValidationUnit, status: str = "passed", **kw) -> UnitResult:  # noqa: ANN003
    return UnitResult(unit=u, status=status, **kw)


def bar(ts: datetime, o: float = 100, h: float = 105, low: float = 95,
        c: float = 102, v: int = 1000) -> OHLCVBar:
    return OHLCVBar(ts=ts, open=o, high=h, low=low, close=c, volume=v)


# --- durable progress ----------------------------------------------------
def test_recorded_units_are_not_repeated(store: CheckpointStore) -> None:
    run = store.start_run("yahoo")
    store.record(run, result(unit("TCS", Timeframe.d1)))
    assert store.completed_keys(run) == {("TCS", "NSE", "1d")}


def test_progress_survives_a_new_store_instance(tmp_path) -> None:  # noqa: ANN001
    """Resumption must work across processes, not just within one."""
    path = tmp_path / "progress.sqlite"
    first = CheckpointStore(path)
    run = first.start_run("yahoo")
    first.record(run, result(unit("TCS"), bars=10))

    reopened = CheckpointStore(path)
    assert reopened.latest_run() == run
    assert reopened.completed_keys(run) == {("TCS", "NSE", "1d")}


def test_failed_units_can_be_re_queued(store: CheckpointStore) -> None:
    run = store.start_run("yahoo")
    store.record(run, result(unit("TCS"), status="failed"))
    assert store.completed_keys(run, include_failed=True) == {("TCS", "NSE", "1d")}
    assert store.completed_keys(run, include_failed=False) == set()


def test_recording_the_same_unit_twice_updates_rather_than_duplicates(
    store: CheckpointStore,
) -> None:
    run = store.start_run("yahoo")
    store.record(run, result(unit("TCS"), bars=5))
    store.record(run, result(unit("TCS"), bars=9))
    stats = store.stats(run)
    assert stats["units_recorded"] == 1
    assert stats["total_bars"] == 9


def test_findings_are_retrievable_for_reporting(store: CheckpointStore) -> None:
    run = store.start_run("yahoo")
    store.record(run, result(
        unit("TCS"), status="failed",
        findings=[Finding("bad_thing", CRITICAL, "it broke")],
    ))
    found = list(store.findings(run))
    assert len(found) == 1
    assert found[0]["code"] == "bad_thing"
    assert found[0]["symbol"] == "TCS"


def test_runs_are_isolated_from_each_other(store: CheckpointStore) -> None:
    a = store.start_run("yahoo", run_id="a")
    b = store.start_run("yahoo", run_id="b")
    store.record(a, result(unit("TCS")))
    assert store.completed_keys(a) == {("TCS", "NSE", "1d")}
    assert store.completed_keys(b) == set()


# --- batching / queue ----------------------------------------------------
def _instrument(db, symbol: str) -> Instrument:  # noqa: ANN001
    row = Instrument(
        trading_symbol=symbol, name=symbol, exchange=Exchange.NSE, is_active=True
    )
    db.add(row)
    db.commit()
    return row


def test_pending_units_skip_what_is_already_done(db, store) -> None:  # noqa: ANN001
    for symbol in ("AAA", "BBB"):
        _instrument(db, symbol)
    validator = LiveMarketDataValidator(
        db=db, service=None, store=store,
        calendar=MarketCalendarService(db),
        timeframes=(Timeframe.d1, Timeframe.h1),
    )
    instruments = validator.universe()
    run = store.start_run("yahoo")
    assert validator.total_units(instruments) == 4

    store.record(run, result(unit("AAA", Timeframe.d1)))
    pending = list(validator.pending_units(run, instruments))
    assert len(pending) == 3
    assert unit("AAA", Timeframe.d1) not in pending


def test_universe_ordering_is_stable(db, store) -> None:  # noqa: ANN001
    """Deterministic ordering is what makes batch N+1 continue from batch N."""
    for symbol in ("CCC", "AAA", "BBB"):
        _instrument(db, symbol)
    validator = LiveMarketDataValidator(db=db, service=None, store=store)
    first = [i.trading_symbol for i in validator.universe()]
    second = [i.trading_symbol for i in validator.universe()]
    assert first == second == ["AAA", "BBB", "CCC"]


def test_inactive_instruments_are_excluded_from_the_queue(db, store) -> None:  # noqa: ANN001
    _instrument(db, "LIVE")
    dead = _instrument(db, "DEAD")
    dead.is_active = False
    db.commit()
    validator = LiveMarketDataValidator(db=db, service=None, store=store)
    assert [i.trading_symbol for i in validator.universe()] == ["LIVE"]


# --- bar-level checks ----------------------------------------------------
def test_future_dated_bars_are_flagged() -> None:
    ahead = datetime.now(UTC) + timedelta(days=30)
    codes = [f.code for f in check_timezone([bar(ahead)], Exchange.NSE)]
    assert "future_timestamp" in codes


def test_out_of_order_bars_are_flagged() -> None:
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    findings = check_monotonic([bar(base + timedelta(days=1)), bar(base)])
    assert [f.code for f in findings] == ["non_monotonic"]


def test_ordered_bars_produce_no_finding() -> None:
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    assert check_monotonic([bar(base), bar(base + timedelta(days=1))]) == []


def test_large_overnight_gap_suggests_unadjusted_action() -> None:
    """An unapplied 1:2 split reads as a ~50% overnight crash."""
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    bars = [
        bar(base, o=990, h=1010, low=980, c=1000),
        bar(base + timedelta(days=1), o=400, h=520, low=390, c=510),   # -60%
    ]
    codes = [f.code for f in check_price_sanity(bars)]
    assert "unexplained_price_jump" in codes


def test_ordinary_daily_moves_are_not_flagged_as_jumps() -> None:
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    bars = [
        bar(base, o=99, h=101, low=98, c=100),
        bar(base + timedelta(days=1), o=104, h=106, low=103, c=105),   # +4%
    ]
    assert [f.code for f in check_price_sanity(bars)] == []


def test_all_zero_volume_is_flagged_for_equities() -> None:
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    bars = [bar(base + timedelta(days=i), v=0) for i in range(3)]
    codes = [f.code for f in check_price_sanity(bars, AssetClass.equity)]
    assert "all_zero_volume" in codes


def test_zero_volume_is_not_flagged_for_indices() -> None:
    """Indices are computed levels with no traded volume — zero is correct there."""
    base = datetime(2026, 1, 5, 10, tzinfo=UTC)
    bars = [bar(base + timedelta(days=i), v=0) for i in range(3)]
    assert check_price_sanity(bars, AssetClass.index) == []


def test_grid_offset_is_information_not_a_warning(db) -> None:  # noqa: ANN001
    """A 30m bar labelled 09:00 for a 09:15 open is a vendor convention.

    Reporting it at the same severity as a genuinely stray timestamp would make
    the warning channel useless.
    """
    calendar = MarketCalendarService(db)
    bars = [bar(datetime(2026, 1, 5, 9, 0, tzinfo=IST))]
    findings = check_session_alignment(bars, Exchange.NSE, Timeframe.m30, calendar)
    assert [f.code for f in findings] == ["session_grid_offset"]
    assert findings[0].severity != WARNING


def test_genuinely_stray_bar_is_a_warning(db) -> None:  # noqa: ANN001
    calendar = MarketCalendarService(db)
    bars = [bar(datetime(2026, 1, 5, 3, 0, tzinfo=IST))]   # hours before any session
    findings = check_session_alignment(bars, Exchange.NSE, Timeframe.m30, calendar)
    assert [f.code for f in findings] == ["outside_session"]


def test_calendar_check_ignores_period_labelled_timeframes(db) -> None:  # noqa: ANN001
    """Monthly bars are stamped with the 1st, often a weekend."""
    calendar = MarketCalendarService(db)
    saturday = [bar(datetime(2022, 1, 1, 0, 0, tzinfo=IST))]
    assert check_calendar_alignment(saturday, Exchange.NSE, Timeframe.mo1, calendar) == []


def test_calendar_check_flags_a_daily_bar_on_a_known_holiday(db) -> None:  # noqa: ANN001
    holiday = datetime(2026, 1, 26, 0, 0, tzinfo=IST)
    seed_calendar(db, entries=[(holiday.date(), SessionType.holiday, "Republic Day")])
    calendar = MarketCalendarService(db)
    findings = check_calendar_alignment([bar(holiday)], Exchange.NSE, Timeframe.d1, calendar)
    assert [f.code for f in findings] == ["non_trading_day_bar"]


def test_synthetic_forward_fill_is_flagged_outside_calendar_coverage(db) -> None:  # noqa: ANN001
    """Yahoo forward-fills NSE holidays with zero-volume flat bars.

    Inside covered years quarantine removes them; outside, this is the only thing
    standing between the series and phantom zero-return trading days.
    """
    seed_calendar(db, entries=[(datetime(2026, 1, 26).date(), SessionType.holiday, "RD")])
    calendar = MarketCalendarService(db)
    filled = bar(datetime(2019, 8, 15, 0, 0, tzinfo=IST), o=100, h=100, low=100, c=100, v=0)
    findings = check_synthetic_bars([filled], Exchange.NSE, Timeframe.d1, calendar)
    assert [f.code for f in findings] == ["synthetic_bar_outside_calendar_coverage"]


def test_real_bars_outside_coverage_are_not_flagged_as_synthetic(db) -> None:  # noqa: ANN001
    calendar = MarketCalendarService(db)
    traded = bar(datetime(2019, 8, 14, 0, 0, tzinfo=IST), v=5000)
    assert check_synthetic_bars([traded], Exchange.NSE, Timeframe.d1, calendar) == []


def test_synthetic_check_only_applies_to_daily_bars(db) -> None:  # noqa: ANN001
    calendar = MarketCalendarService(db)
    filled = bar(datetime(2019, 8, 15, 10, 0, tzinfo=IST), o=100, h=100, low=100, c=100, v=0)
    assert check_synthetic_bars([filled], Exchange.NSE, Timeframe.m5, calendar) == []


def test_calendar_check_stays_silent_outside_covered_years(db) -> None:  # noqa: ANN001
    """No coverage means no authority — never a violation."""
    seed_calendar(db, entries=[(datetime(2026, 1, 26).date(), SessionType.holiday, "RD")])
    calendar = MarketCalendarService(db)
    uncovered = [bar(datetime(2019, 3, 4, 0, 0, tzinfo=IST))]
    assert check_calendar_alignment(uncovered, Exchange.NSE, Timeframe.d1, calendar) == []
