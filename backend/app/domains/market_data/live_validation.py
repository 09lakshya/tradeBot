"""Live validation harness for the Market Data Layer.

Validates the *entire* discovered universe against a live provider rather than a
curated sample. Because no free provider will serve tens of thousands of
symbol×timeframe requests in one sitting, the work is modelled as a queue of
independent units with durable per-unit progress: a run can be interrupted at any
point — rate limit, outage, machine reboot — and resumed without redoing work.

The harness deliberately drives the *real* ingestion path
(``MarketDataService.sync_ohlcv``): provider → quality validation → quarantine →
corporate-action adjustment → upsert. Validating a parallel code path would prove
nothing about the pipeline that actually runs in production.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.enums import AssetClass, Exchange, Timeframe
from app.domains.market_data.models import Instrument, QuarantinedData
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics
from app.domains.market_data.providers.base import ProviderError
from app.domains.market_data.schemas import OHLCVBar
from app.domains.market_data.service import MarketDataService
from app.domains.market_data.sessions import exchange_timezone
from app.domains.market_data.validation import CALENDAR_CHECKED

log = get_logger(__name__)

CRITICAL, ERROR, WARNING, INFO = "critical", "error", "warning", "info"

#: How far back to request each timeframe. These are provider realities, not
#: preferences: intraday history is short-lived at every free vendor, so asking
#: for a year of 1m data would fail everywhere and prove nothing.
LOOKBACK_DAYS: dict[Timeframe, int] = {
    Timeframe.m1: 5,
    Timeframe.m5: 30,
    Timeframe.m15: 30,
    Timeframe.m30: 30,
    Timeframe.h1: 45,
    Timeframe.h4: 45,
    Timeframe.d1: 365,
    Timeframe.w1: 730,
    Timeframe.mo1: 1825,
}

ALL_TIMEFRAMES: tuple[Timeframe, ...] = tuple(Timeframe)


@dataclass(frozen=True)
class ValidationUnit:
    """The atom of work: one instrument at one timeframe."""

    symbol: str
    exchange: Exchange
    timeframe: Timeframe
    #: Advisory: refines class-specific checks (e.g. indices carry no volume).
    #: Not part of the identity key, so resumption is unaffected by it.
    asset_class: AssetClass | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.symbol, self.exchange.value, self.timeframe.value)


@dataclass
class Finding:
    code: str
    severity: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class UnitResult:
    unit: ValidationUnit
    status: str                      # "passed" | "failed" | "no_data"
    bars: int = 0
    quarantined: int = 0
    missing_intervals: int = 0
    latency_ms: float = 0.0
    findings: list[Finding] = field(default_factory=list)

    @property
    def worst_severity(self) -> str | None:
        for level in (CRITICAL, ERROR, WARNING, INFO):
            if any(f.severity == level for f in self.findings):
                return level
        return None


# ---------------------------------------------------------------------------
# Durable progress
# ---------------------------------------------------------------------------
class CheckpointStore:
    """SQLite-backed progress ledger.

    Deliberately independent of the application database: progress must survive
    exactly the failures (DB down, migration in flight) that make a validation
    run worth resuming. Each unit is committed as it completes, so the process
    can die at any instant and lose at most the in-flight unit.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id      TEXT PRIMARY KEY,
                    started_at  TEXT NOT NULL,
                    provider    TEXT,
                    note        TEXT
                );
                CREATE TABLE IF NOT EXISTS progress (
                    run_id      TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    exchange    TEXT NOT NULL,
                    timeframe   TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    bars        INTEGER DEFAULT 0,
                    quarantined INTEGER DEFAULT 0,
                    missing     INTEGER DEFAULT 0,
                    latency_ms  REAL DEFAULT 0,
                    findings    TEXT,
                    updated_at  TEXT NOT NULL,
                    PRIMARY KEY (run_id, symbol, exchange, timeframe)
                );
                CREATE INDEX IF NOT EXISTS ix_progress_status
                    ON progress (run_id, status);
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    # --- run lifecycle ---------------------------------------------------
    def start_run(self, provider: str, note: str = "", run_id: str | None = None) -> str:
        run_id = run_id or uuid.uuid4().hex[:12]
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO runs (run_id, started_at, provider, note) "
                "VALUES (?, ?, ?, ?)",
                (run_id, datetime.now(UTC).isoformat(), provider, note),
            )
            conn.commit()
        return run_id

    def latest_run(self) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return row["run_id"] if row else None

    # --- per-unit progress -----------------------------------------------
    def completed_keys(self, run_id: str, include_failed: bool = True) -> set[tuple[str, str, str]]:
        """Units already done, so a resumed run skips straight past them."""
        query = "SELECT symbol, exchange, timeframe FROM progress WHERE run_id = ?"
        params: list[object] = [run_id]
        if not include_failed:
            query += " AND status != 'failed'"
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return {(r["symbol"], r["exchange"], r["timeframe"]) for r in rows}

    def record(self, run_id: str, result: UnitResult) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO progress (run_id, symbol, exchange, timeframe, status,
                                      bars, quarantined, missing, latency_ms,
                                      findings, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (run_id, symbol, exchange, timeframe) DO UPDATE SET
                    status=excluded.status, bars=excluded.bars,
                    quarantined=excluded.quarantined, missing=excluded.missing,
                    latency_ms=excluded.latency_ms, findings=excluded.findings,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id, result.unit.symbol, result.unit.exchange.value,
                    result.unit.timeframe.value, result.status, result.bars,
                    result.quarantined, result.missing_intervals,
                    round(result.latency_ms, 2),
                    json.dumps([f.as_dict() for f in result.findings]),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()

    def stats(self, run_id: str) -> dict[str, object]:
        with closing(self._connect()) as conn:
            by_status = {
                r["status"]: r["n"] for r in conn.execute(
                    "SELECT status, COUNT(*) n FROM progress WHERE run_id = ? "
                    "GROUP BY status", (run_id,)
                )
            }
            totals = conn.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(bars),0) bars, "
                "COALESCE(SUM(quarantined),0) q, COALESCE(SUM(missing),0) m, "
                "COALESCE(AVG(latency_ms),0) lat FROM progress WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            by_tf = {
                r["timeframe"]: r["n"] for r in conn.execute(
                    "SELECT timeframe, COUNT(*) n FROM progress WHERE run_id = ? "
                    "GROUP BY timeframe", (run_id,)
                )
            }
        return {
            "units_recorded": totals["n"],
            "by_status": by_status,
            "by_timeframe": by_tf,
            "total_bars": totals["bars"],
            "total_quarantined": totals["q"],
            "total_missing_intervals": totals["m"],
            "avg_unit_latency_ms": round(totals["lat"], 2),
        }

    def findings(self, run_id: str) -> Iterator[dict[str, object]]:
        with closing(self._connect()) as conn:
            for row in conn.execute(
                "SELECT symbol, exchange, timeframe, status, findings FROM progress "
                "WHERE run_id = ? AND findings != '[]'", (run_id,)
            ):
                for item in json.loads(row["findings"]):
                    yield {
                        "symbol": row["symbol"], "exchange": row["exchange"],
                        "timeframe": row["timeframe"], "status": row["status"], **item,
                    }


# ---------------------------------------------------------------------------
# Bar-level checks beyond DataQualityValidator
# ---------------------------------------------------------------------------
def check_timezone(bars: list[OHLCVBar], exchange: Exchange) -> list[Finding]:
    """Every bar must be timezone-aware and land on a sane exchange-local time."""
    findings: list[Finding] = []
    naive = [b for b in bars if b.ts.tzinfo is None]
    if naive:
        findings.append(Finding(
            "naive_timestamp", CRITICAL,
            f"{len(naive)} bars carry no timezone; UTC conversion would be a guess",
        ))
    tz = exchange_timezone(exchange)
    future = [b for b in bars if b.ts > datetime.now(UTC) + timedelta(days=1)]
    if future:
        findings.append(Finding(
            "future_timestamp", ERROR,
            f"{len(future)} bars are dated in the future (latest {max(b.ts for b in future)})",
        ))
    if bars:
        # A daily bar must resolve to a single exchange-local calendar date.
        local = bars[0].ts.astimezone(tz)
        if local.utcoffset() is None:
            findings.append(Finding(
                "tz_conversion_failed", CRITICAL,
                f"cannot express bar in {tz.key}",
            ))
    return findings


def check_monotonic(bars: list[OHLCVBar]) -> list[Finding]:
    out_of_order = sum(
        1 for a, b in zip(bars, bars[1:], strict=False) if b.ts <= a.ts
    )
    if out_of_order:
        return [Finding(
            "non_monotonic", ERROR,
            f"{out_of_order} bars are not in strictly ascending time order",
        )]
    return []


def check_session_alignment(
    bars: list[OHLCVBar], exchange: Exchange, timeframe: Timeframe,
    calendar: MarketCalendarService,
) -> list[Finding]:
    """Intraday bars must fall inside the exchange's trading window.

    Two very different things can put a bar outside that window, and conflating
    them buries the one that matters:

    * **Grid alignment** — the vendor labels bars on a wall-clock grid rather than
      from the session open, so the day's first bar is stamped up to one bar-width
      early (Yahoo's 30m bars start at 09:00 for a 09:15 open). The data is sound;
      only the label convention differs.
    * **Genuinely stray bars** — timestamps well outside any session, which point
      at a timezone error or corrupt data.
    """
    if not timeframe.is_intraday or not bars:
        return []
    tz = exchange_timezone(exchange)
    grid_early = 0
    stray = 0
    for bar in bars:
        local = bar.ts.astimezone(tz)
        hours = calendar.trading_hours(exchange, local.date())
        if hours is None:
            stray += 1
            continue
        open_t, close_t = hours
        if open_t <= local.time() <= close_t:
            continue
        open_dt = local.replace(
            hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0
        )
        lead = (open_dt - local).total_seconds()
        if 0 < lead < timeframe.seconds:
            grid_early += 1
        else:
            stray += 1

    findings: list[Finding] = []
    if grid_early:
        findings.append(Finding(
            "session_grid_offset", INFO,
            f"{grid_early}/{len(bars)} bars are labelled on a wall-clock grid up to "
            f"one interval before the {exchange.value} open — provider labelling "
            "convention, not missing or corrupt data",
        ))
    if stray:
        findings.append(Finding(
            "outside_session", WARNING,
            f"{stray}/{len(bars)} intraday bars fall outside the "
            f"{exchange.value} session window",
        ))
    return findings


def check_calendar_alignment(
    bars: list[OHLCVBar], exchange: Exchange, timeframe: Timeframe,
    calendar: MarketCalendarService,
) -> list[Finding]:
    """Flag bars dated to a provable market closure.

    Mirrors the quarantine rule exactly — same "provably closed" test, same
    restriction to timeframes whose timestamp denotes a real session. Validation
    that applied a stricter rule than ingestion would report failures on data the
    pipeline had already, correctly, accepted.
    """
    if timeframe not in CALENDAR_CHECKED:
        return []
    tz = exchange_timezone(exchange)
    bad = [
        b for b in bars
        if calendar.is_known_non_trading_day(exchange, b.ts.astimezone(tz).date())
    ]
    if bad:
        sample = ", ".join(str(b.ts.astimezone(tz).date()) for b in bad[:3])
        return [Finding(
            "non_trading_day_bar", ERROR,
            f"{len(bad)} bars land on non-trading days (e.g. {sample})",
        )]
    return []


def check_synthetic_bars(
    bars: list[OHLCVBar], exchange: Exchange, timeframe: Timeframe,
    calendar: MarketCalendarService,
) -> list[Finding]:
    """Detect forward-filled placeholder bars the calendar cannot reach.

    Yahoo emits a bar for every NSE holiday, carrying the previous close with
    zero volume and O=H=L=C. Where the calendar has coverage these are already
    quarantined; outside it they would silently enter the series as extra
    zero-return trading days, deflating measured volatility and diluting every
    moving average computed over them.

    Reported rather than quarantined: a genuinely untraded session on an illiquid
    scrip has the same shape, and this predicate alone cannot separate the two.
    """
    if timeframe is not Timeframe.d1 or not bars:
        return []
    tz = exchange_timezone(exchange)
    uncovered = [
        b for b in bars
        if b.volume == 0
        and b.open == b.high == b.low == b.close
        and not calendar.has_authoritative_coverage(exchange, b.ts.astimezone(tz).date())
    ]
    if not uncovered:
        return []
    years = sorted({b.ts.astimezone(tz).year for b in uncovered})
    return [Finding(
        "synthetic_bar_outside_calendar_coverage", WARNING,
        f"{len(uncovered)} zero-volume flat-OHLC bars in year(s) {years} where the "
        "calendar has no coverage — likely provider forward-fill on a market holiday",
    )]


def check_price_sanity(
    bars: list[OHLCVBar], asset_class: AssetClass | None = None
) -> list[Finding]:
    """Catch unadjusted corporate actions: a clean split looks like a 50% crash."""
    findings: list[Finding] = []
    jumps = 0
    for prev, cur in zip(bars, bars[1:], strict=False):
        if prev.close <= 0:
            continue
        change = abs(cur.open - prev.close) / prev.close
        if change > 0.5:
            jumps += 1
    if jumps:
        findings.append(Finding(
            "unexplained_price_jump", WARNING,
            f"{jumps} bar-to-bar gaps exceed 50%, suggesting an unadjusted "
            "corporate action or a bad print",
        ))
    # Indices are computed levels with no traded volume, so zero volume there is
    # correct, not a defect. Only flag it where volume is expected.
    if asset_class is not AssetClass.index:
        zero_volume = sum(1 for b in bars if b.volume == 0)
        if bars and zero_volume == len(bars):
            findings.append(Finding(
                "all_zero_volume", WARNING,
                "every bar reports zero volume",
            ))
    return findings


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------
@dataclass
class BatchOutcome:
    run_id: str
    attempted: int = 0
    passed: int = 0
    failed: int = 0
    no_data: int = 0
    skipped_resumed: int = 0
    duration_seconds: float = 0.0
    exhausted: bool = False          # True when the whole queue is done

    def summary(self) -> dict[str, object]:
        return {
            "run_id": self.run_id, "attempted": self.attempted,
            "passed": self.passed, "failed": self.failed, "no_data": self.no_data,
            "already_done": self.skipped_resumed,
            "queue_exhausted": self.exhausted,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class LiveMarketDataValidator:
    """Runs resumable, batched validation over the discovered instrument universe."""

    def __init__(
        self,
        db: Session,
        service: MarketDataService,
        store: CheckpointStore,
        calendar: MarketCalendarService | None = None,
        metrics: MetricsCollector | None = None,
        timeframes: Iterable[Timeframe] = ALL_TIMEFRAMES,
        pause_seconds: float = 0.0,
    ) -> None:
        self._db = db
        self._service = service
        self._store = store
        self._calendar = calendar or MarketCalendarService(db)
        self._metrics = metrics or default_metrics
        self._timeframes = tuple(timeframes)
        self._pause = pause_seconds

    # --- work queue -------------------------------------------------------
    def universe(
        self,
        exchanges: set[Exchange] | None = None,
        asset_classes: set[AssetClass] | None = None,
        limit: int | None = None,
    ) -> list[Instrument]:
        """Tradable instruments from the Instrument Master, ordered deterministically.

        Deterministic ordering is what makes resumption meaningful: batch N+1 must
        pick up exactly where batch N stopped, across processes and days.
        """
        stmt = select(Instrument).where(
            Instrument.is_active.is_(True), Instrument.is_delisted.is_(False)
        )
        if exchanges:
            stmt = stmt.where(Instrument.exchange.in_(exchanges))
        if asset_classes:
            stmt = stmt.where(Instrument.asset_class.in_(asset_classes))
        stmt = stmt.order_by(Instrument.exchange, Instrument.trading_symbol)
        if limit:
            stmt = stmt.limit(limit)
        return list(self._db.execute(stmt).scalars())

    def pending_units(
        self,
        run_id: str,
        instruments: list[Instrument],
        retry_failed: bool = False,
    ) -> Iterator[ValidationUnit]:
        done = self._store.completed_keys(run_id, include_failed=not retry_failed)
        for instrument in instruments:
            for timeframe in self._timeframes:
                unit = ValidationUnit(
                    instrument.trading_symbol, instrument.exchange, timeframe,
                    asset_class=instrument.asset_class,
                )
                if unit.key in done:
                    continue
                yield unit

    def total_units(self, instruments: list[Instrument]) -> int:
        return len(instruments) * len(self._timeframes)

    # --- execution --------------------------------------------------------
    def run_batch(
        self,
        run_id: str,
        instruments: list[Instrument],
        batch_size: int,
        retry_failed: bool = False,
    ) -> BatchOutcome:
        """Validate up to ``batch_size`` outstanding units, then return.

        Returning after a bounded amount of work — rather than looping until the
        market is exhausted — is what lets a scheduler run this repeatedly under a
        provider's daily quota until coverage reaches 100%.
        """
        started = time.perf_counter()
        outcome = BatchOutcome(run_id=run_id)
        # Counted against *this* batch's instruments, not the whole ledger — batches
        # are usually filtered by exchange or asset class, so a global count would
        # report work from unrelated slices as already done here.
        done = self._store.completed_keys(run_id, include_failed=not retry_failed)
        outcome.skipped_resumed = sum(
            1
            for instrument in instruments
            for timeframe in self._timeframes
            if (instrument.trading_symbol, instrument.exchange.value, timeframe.value) in done
        )

        pending = self.pending_units(run_id, instruments, retry_failed=retry_failed)
        for unit in pending:
            if outcome.attempted >= batch_size:
                break
            result = self.validate_unit(unit)
            self._store.record(run_id, result)
            outcome.attempted += 1
            if result.status == "passed":
                outcome.passed += 1
            elif result.status == "no_data":
                outcome.no_data += 1
            else:
                outcome.failed += 1
            if self._pause:
                time.sleep(self._pause)
        else:
            outcome.exhausted = True

        outcome.duration_seconds = time.perf_counter() - started
        log.info("validation_batch_complete", **outcome.summary())
        return outcome

    def validate_unit(self, unit: ValidationUnit) -> UnitResult:
        """Drive one instrument×timeframe through the real ingestion pipeline."""
        started = time.perf_counter()
        end = date.today()
        start = end - timedelta(days=LOOKBACK_DAYS.get(unit.timeframe, 365))
        result = UnitResult(unit=unit, status="passed")

        try:
            summary = self._service.sync_ohlcv(
                unit.symbol, unit.exchange, unit.timeframe, start, end, adjust=True
            )
        except ProviderError as exc:
            result.status = "no_data"
            result.findings.append(Finding(
                "provider_error", WARNING, f"{type(exc).__name__}: {exc}"
            ))
            result.latency_ms = (time.perf_counter() - started) * 1000
            return result
        except ValueError as exc:
            result.status = "failed"
            result.findings.append(Finding("unknown_instrument", ERROR, str(exc)))
            result.latency_ms = (time.perf_counter() - started) * 1000
            return result
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the run
            result.status = "failed"
            result.findings.append(Finding(
                "unhandled_exception", CRITICAL, f"{type(exc).__name__}: {exc}"
            ))
            result.latency_ms = (time.perf_counter() - started) * 1000
            return result

        result.bars = summary["valid"]
        result.quarantined = summary["quarantined"]
        result.missing_intervals = summary["missing_intervals"]

        if summary["fetched"] == 0:
            result.status = "no_data"
            result.findings.append(Finding(
                "empty_response", WARNING, "provider returned no bars for the window"
            ))
            result.latency_ms = (time.perf_counter() - started) * 1000
            return result

        # Re-read what was persisted: this validates the *stored* series, which is
        # what strategies will consume, not just what the provider happened to send.
        stored = self._service.get_ohlcv(
            unit.symbol, unit.exchange, unit.timeframe, start, end
        )
        if not stored and result.bars:
            result.findings.append(Finding(
                "persisted_but_unreadable", CRITICAL,
                f"{result.bars} bars were written but the read path returned none "
                "— storage/query timezone boundaries disagree",
            ))

        result.findings.extend(check_timezone(stored, unit.exchange))
        result.findings.extend(check_monotonic(stored))
        result.findings.extend(
            check_calendar_alignment(stored, unit.exchange, unit.timeframe, self._calendar)
        )
        result.findings.extend(
            check_session_alignment(stored, unit.exchange, unit.timeframe, self._calendar)
        )
        result.findings.extend(
            check_synthetic_bars(stored, unit.exchange, unit.timeframe, self._calendar)
        )
        result.findings.extend(check_price_sanity(stored, unit.asset_class))

        if result.quarantined:
            result.findings.append(Finding(
                "quarantined_bars", INFO,
                f"{result.quarantined} bars rejected by data-quality validation",
            ))

        worst = result.worst_severity
        if worst in (CRITICAL, ERROR):
            result.status = "failed"
        result.latency_ms = (time.perf_counter() - started) * 1000
        self._metrics.observe_latency(
            "validation_unit", result.latency_ms, timeframe=unit.timeframe.value
        )
        return result

    # --- reporting --------------------------------------------------------
    def coverage(self, run_id: str, instruments: list[Instrument]) -> dict[str, object]:
        """Progress of ``instruments`` within ``run_id``.

        The completed count is intersected with the given instrument set rather
        than read off the whole ledger: a run accumulates batches across different
        exchanges and asset classes, so a global count divided by one slice's
        denominator reports nonsense (coverage above 100%).
        """
        total = self.total_units(instruments)
        stats = self._store.stats(run_id)
        done = self._store.completed_keys(run_id)
        recorded = sum(
            1
            for instrument in instruments
            for timeframe in self._timeframes
            if (instrument.trading_symbol, instrument.exchange.value, timeframe.value) in done
        )
        return {
            **stats,
            "universe_instruments": len(instruments),
            "timeframes": [t.value for t in self._timeframes],
            "total_units": total,
            "units_completed_here": recorded,
            "coverage_pct": round(100 * recorded / total, 2) if total else 0.0,
            "remaining_units": max(total - recorded, 0),
        }

    def quarantine_breakdown(self) -> dict[str, int]:
        rows = self._db.execute(
            select(QuarantinedData.reason, func.count()).group_by(QuarantinedData.reason)
        ).all()
        return {reason.value: count for reason, count in rows}
