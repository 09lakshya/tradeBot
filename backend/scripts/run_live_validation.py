"""Live validation runner for the Market Data Layer.

Operational tooling, not application code: it wires the real domain services to a
live provider, drives the whole market through them in resumable batches, and
writes a report.

    python backend/scripts/run_live_validation.py discover
    python backend/scripts/run_live_validation.py validate --batch-size 400
    python backend/scripts/run_live_validation.py providers
    python backend/scripts/run_live_validation.py report

Every subcommand is safe to re-run. ``validate`` resumes from the checkpoint
ledger, so repeated invocations march coverage toward 100% under whatever rate
limit the provider imposes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Config is read at import time, so environment defaults must be set first. These
# are validation-run defaults only; nothing here touches a production .env.
os.environ.setdefault("SECRET_KEY", "live-validation-run-key-not-for-production")
os.environ.setdefault("POSTGRES_USER", "validation")
os.environ.setdefault("POSTGRES_PASSWORD", "validation")
os.environ.setdefault("POSTGRES_DB", "validation")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("MARKET_DATA_PROVIDER", "yahoo")

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.domains.market_data.calendar import MarketCalendarService, sync_calendar  # noqa: E402
from app.domains.market_data.discovery import InstrumentUniverseService  # noqa: E402
from app.domains.market_data.enums import (  # noqa: E402
    AssetClass,
    Exchange,
    Timeframe,
)
from app.domains.market_data.live_validation import (  # noqa: E402
    ALL_TIMEFRAMES,
    CheckpointStore,
    LiveMarketDataValidator,
)
from app.domains.market_data.models import OHLCV, Instrument  # noqa: E402
from app.domains.market_data.observability import metrics  # noqa: E402
from app.domains.market_data.providers.base import ProviderError  # noqa: E402
from app.domains.market_data.providers.registry import build_router  # noqa: E402
from app.domains.market_data.providers.resilience import RetryPolicy  # noqa: E402
from app.domains.market_data.service import MarketDataService  # noqa: E402
from app.models import Base  # noqa: E402

ARTIFACTS = REPO_ROOT / "validation_artifacts"
DB_PATH = ARTIFACTS / "market_data.sqlite"
CHECKPOINT_PATH = ARTIFACTS / "validation_progress.sqlite"


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
def make_session() -> Session:
    """Local SQLite store standing in for TimescaleDB.

    The production target is Postgres + TimescaleDB; SQLite is used here only so
    the *ingestion path* can be exercised end to end without a server. Everything
    it validates (provider behaviour, normalization, quality rules, adjustment,
    timezone handling) is storage-agnostic. Hypertable behaviour and the Postgres
    upsert plan are explicitly out of scope for this run and flagged in the report.
    """
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    url = os.environ.get("VALIDATION_DATABASE_URL", f"sqlite+pysqlite:///{DB_PATH}")
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def make_service(db: Session) -> MarketDataService:
    router = build_router(primary=os.environ["MARKET_DATA_PROVIDER"], metrics=metrics)
    router._retry = RetryPolicy(max_attempts=2, base_delay=0.4)  # noqa: SLF001
    return MarketDataService(
        db=db, provider=router, metrics=metrics,
        calendar=MarketCalendarService(db),
    )


def write_json(name: str, payload: object) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def rss_mb() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------
def cmd_discover(args: argparse.Namespace) -> int:
    db = make_session()
    tracemalloc.start()
    cpu_start, wall_start = time.process_time(), time.perf_counter()

    calendar_sync = sync_calendar(db)
    service = InstrumentUniverseService(db=db, metrics=metrics)
    report = service.discover()
    reconciliation = service.reconcile(report)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    calendar_service = MarketCalendarService(db)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "calendar_sync": calendar_sync,
        "calendar_coverage": {
            exchange.value: sorted(calendar_service.covered_years(exchange))
            for exchange in (Exchange.NSE, Exchange.BSE)
        },
        "discovery": report.summary(),
        "per_source": [
            {
                "source": r.source, "exchange": r.exchange.value,
                "asset_class": r.asset_class.value, "ok": r.ok,
                "count": r.count, "seconds": r.duration_seconds, "error": r.error,
            }
            for r in report.results
        ],
        "reconciliation": reconciliation.summary(),
        "duplicates": [
            {
                "kind": d.kind, "identity": d.identity,
                "exchange": d.exchange.value if d.exchange else None,
                "members": d.members, "sources": d.sources,
            }
            for d in report.duplicates[: args.max_duplicates]
        ],
        "duplicate_total": len(report.duplicates),
        "performance": {
            "wall_seconds": round(time.perf_counter() - wall_start, 2),
            "cpu_seconds": round(time.process_time() - cpu_start, 2),
            "peak_traced_memory_mb": round(peak / (1024 * 1024), 1),
            "rss_mb": rss_mb(),
        },
    }
    path = write_json("discovery_report.json", payload)
    print(json.dumps(payload["discovery"], indent=2, default=str))
    print(json.dumps(payload["reconciliation"], indent=2, default=str))
    print(f"\nwrote {path}")
    db.close()
    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------
def _timeframes(spec: str) -> tuple[Timeframe, ...]:
    if spec == "all":
        return ALL_TIMEFRAMES
    return tuple(Timeframe(v.strip()) for v in spec.split(",") if v.strip())


def cmd_validate(args: argparse.Namespace) -> int:
    db = make_session()
    service = make_service(db)
    store = CheckpointStore(CHECKPOINT_PATH)
    # Continue the most recent run unless one is named, so plain re-invocation
    # extends coverage instead of starting over. start_run is INSERT OR IGNORE.
    run_id = args.run_id or store.latest_run() or uuid.uuid4().hex[:12]
    store.start_run(os.environ["MARKET_DATA_PROVIDER"], "full-market validation", run_id)

    validator = LiveMarketDataValidator(
        db=db, service=service, store=store,
        calendar=MarketCalendarService(db), metrics=metrics,
        timeframes=_timeframes(args.timeframes),
        pause_seconds=args.pause,
    )

    exchanges = {Exchange(e) for e in args.exchanges.split(",")} if args.exchanges else None
    asset_classes = (
        {AssetClass(a) for a in args.asset_classes.split(",")} if args.asset_classes else None
    )
    instruments = validator.universe(
        exchanges=exchanges, asset_classes=asset_classes, limit=args.limit
    )
    if not instruments:
        print("no instruments in the master — run `discover` first", file=sys.stderr)
        return 2

    tracemalloc.start()
    cpu_start = time.process_time()
    outcome = validator.run_batch(
        run_id, instruments, batch_size=args.batch_size, retry_failed=args.retry_failed
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    coverage = validator.coverage(run_id, instruments)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "batch": outcome.summary(),
        "coverage": coverage,
        "quarantine_by_reason": validator.quarantine_breakdown(),
        "performance": {
            "cpu_seconds": round(time.process_time() - cpu_start, 2),
            "peak_traced_memory_mb": round(peak / (1024 * 1024), 1),
            "rss_mb": rss_mb(),
            "units_per_second": (
                round(outcome.attempted / outcome.duration_seconds, 2)
                if outcome.duration_seconds else 0.0
            ),
        },
    }
    write_json("validation_progress.json", payload)
    print(json.dumps(payload, indent=2, default=str))
    db.close()
    return 0


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------
def cmd_providers(args: argparse.Namespace) -> int:
    """Exercise provider-level behaviour against the live endpoint."""
    from app.domains.market_data.providers.mock import MockProvider
    from app.domains.market_data.providers.registry import ProviderRouter

    primary = os.environ["MARKET_DATA_PROVIDER"]
    results: dict[str, object] = {"generated_at": datetime.now(UTC).isoformat()}

    router = build_router(primary=primary, metrics=metrics)
    results["chain"] = router.chain

    # Availability + health, sampled to get a latency distribution.
    healths = []
    for _ in range(args.health_samples):
        health = router.health_check()
        healths.append({
            "provider": health.provider, "status": health.status.value,
            "latency_ms": health.latency_ms, "detail": health.detail,
        })
        time.sleep(0.3)
    results["health_samples"] = healths
    latencies = [h["latency_ms"] for h in healths if h["latency_ms"]]
    results["health_summary"] = {
        "up": sum(1 for h in healths if h["status"] == "up"),
        "degraded": sum(1 for h in healths if h["status"] == "degraded"),
        "down": sum(1 for h in healths if h["status"] == "down"),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
    }

    # Response consistency: the same request twice must agree bar for bar.
    end = date.today()
    start = end - timedelta(days=30)
    try:
        first = router.fetch_ohlcv(args.symbol, Exchange.NSE, Timeframe.d1, start, end)
        second = router.fetch_ohlcv(args.symbol, Exchange.NSE, Timeframe.d1, start, end)
        same = (
            len(first.bars) == len(second.bars)
            and all(
                a.ts == b.ts and a.close == b.close
                for a, b in zip(first.bars, second.bars, strict=False)
            )
        )
        results["consistency"] = {
            "symbol": args.symbol, "bars_first": len(first.bars),
            "bars_second": len(second.bars), "identical": same,
        }
    except ProviderError as exc:
        results["consistency"] = {"error": f"{type(exc).__name__}: {exc}"}

    # Failover: a provider that always fails must be transparently skipped.
    class _AlwaysDown(MockProvider):
        name = "always_down"

        def fetch_ohlcv(self, *a, **kw):  # noqa: ANN002, ANN003, ANN201
            raise ProviderError("simulated outage")

        def health_check(self):  # noqa: ANN201
            raise ProviderError("simulated outage")

    failover_router = ProviderRouter(
        [_AlwaysDown(), MockProvider()], metrics=metrics,
        retry=RetryPolicy(max_attempts=1),
    )
    try:
        resp = failover_router.fetch_ohlcv("TEST", Exchange.NSE, Timeframe.d1, start, end)
        results["failover"] = {
            "chain": failover_router.chain, "served_by": resp.provider,
            "recovered": resp.provider != "always_down",
        }
    except ProviderError as exc:
        results["failover"] = {"chain": failover_router.chain, "error": str(exc)}

    # Recovery: once the primary comes back, traffic must return to it.
    class _Flaky(MockProvider):
        name = "flaky"

        def __init__(self) -> None:
            super().__init__()
            self.down = True

        def fetch_ohlcv(self, *a, **kw):  # noqa: ANN002, ANN003, ANN201
            if self.down:
                raise ProviderError("simulated outage")
            return super().fetch_ohlcv(*a, **kw)

    flaky = _Flaky()
    recovery_router = ProviderRouter(
        [flaky, MockProvider()], metrics=metrics, retry=RetryPolicy(max_attempts=1)
    )
    during = recovery_router.fetch_ohlcv("TEST", Exchange.NSE, Timeframe.d1, start, end)
    flaky.down = False
    after = recovery_router.fetch_ohlcv("TEST", Exchange.NSE, Timeframe.d1, start, end)
    results["recovery"] = {
        "served_during_outage": during.provider,
        "served_after_recovery": after.provider,
        "returned_to_primary": after.provider == "flaky",
    }

    # Rate limiting: a burst beyond the bucket must be throttled, not dropped.
    limited = ProviderRouter(
        [MockProvider()], metrics=metrics, rate_per_sec=5, burst=5,
        retry=RetryPolicy(max_attempts=1),
    )
    burst_start = time.perf_counter()
    served = 0
    for _ in range(15):
        try:
            limited.fetch_ohlcv("TEST", Exchange.NSE, Timeframe.d1, start, end)
            served += 1
        except ProviderError:
            pass
    burst_elapsed = time.perf_counter() - burst_start
    results["rate_limiting"] = {
        "requests": 15, "served": served,
        "elapsed_seconds": round(burst_elapsed, 2),
        "effective_rate_per_sec": round(served / burst_elapsed, 2) if burst_elapsed else None,
        "throttled": burst_elapsed > 1.0,
    }

    # Cache: without Redis the layer must degrade to misses, never crash.
    from app.domains.market_data.cache import MarketCache
    cache = MarketCache(redis_client=None, metrics=metrics)
    cache.set("latest_price", 101.5, "TEST", "NSE")
    results["cache"] = {
        "redis_available": cache.available,
        "read_without_redis": cache.get("latest_price", "TEST", "NSE"),
        "degrades_gracefully": cache.get("latest_price", "TEST", "NSE") is None,
    }

    results["metrics_snapshot"] = metrics.snapshot()
    write_json("provider_report.json", results)
    print(json.dumps(results, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# corporate actions
# ---------------------------------------------------------------------------
def cmd_corporate_actions(args: argparse.Namespace) -> int:
    """Validate that the *stored* series stays continuous across a real split.

    A split that is mis-handled — not applied, or applied twice — leaves a
    discontinuity at the ex-date, which is the single most damaging defect for any
    backtest built on the series. Rather than compare adjustment factors against a
    provider convention we don't control, this checks the property that actually
    matters: the ratio of consecutive closes across the ex-date should be ~1
    (continuous), never ~0.5 (unapplied) or ~2 (double-applied).

    It drives the real pipeline, so it exercises exactly the provider-aware
    adjustment the service performs in production.
    """
    db = make_session()
    service = make_service(db)
    validator = LiveMarketDataValidator(db=db, service=service, store=CheckpointStore(
        CHECKPOINT_PATH))
    instruments = validator.universe(
        exchanges={Exchange.NSE}, asset_classes={AssetClass.equity}, limit=args.scan
    )

    end = date.today()
    start = end - timedelta(days=args.lookback_days)
    checked: list[dict] = []
    scanned = 0

    for instrument in instruments:
        if len(checked) >= args.samples:
            break
        symbol = instrument.trading_symbol
        scanned += 1
        try:
            service.sync_corporate_actions(symbol, Exchange.NSE)
        except ProviderError as exc:
            checked.append({"symbol": symbol, "verdict": "provider_error",
                            "error": f"{type(exc).__name__}: {exc}"})
            continue

        actions = service.load_corporate_actions(instrument.id)
        splits = [
            a for a in actions
            if a.action_type.value in ("split", "bonus") and start <= a.ex_date <= end
            and a.ratio_from and a.ratio_to
        ]
        if not splits:
            continue

        # Ingest through the real pipeline (validation → provider-aware adjustment
        # → store), then read back what was persisted.
        try:
            service.sync_ohlcv(symbol, Exchange.NSE, Timeframe.d1, start, end, adjust=True)
        except (ProviderError, ValueError) as exc:
            checked.append({"symbol": symbol, "verdict": "provider_error",
                            "error": str(exc)})
            continue
        stored = service.get_ohlcv(symbol, Exchange.NSE, Timeframe.d1, start, end)
        stored.sort(key=lambda b: b.ts)

        worst_jump = None
        worst_action = None
        for action in splits:
            before = [b for b in stored if b.ts.date() < action.ex_date]
            after = [b for b in stored if b.ts.date() >= action.ex_date]
            if not before or not after:
                continue
            last, first = before[-1].close, after[0].close
            if last <= 0:
                continue
            # Continuity ratio across the ex-date. ~1 is correct; the split factor
            # (or its inverse) appearing here is an unapplied / double-applied event.
            ratio = first / last
            jump = abs(ratio - 1.0)
            if worst_jump is None or jump > worst_jump:
                worst_jump, worst_action = jump, action

        checked.append({
            "symbol": symbol,
            "actions": [
                {"type": a.action_type.value, "ex_date": str(a.ex_date),
                 "ratio": f"{a.ratio_from:g}:{a.ratio_to:g}"}
                for a in splits
            ],
            "bars": len(stored),
            "worst_continuity_gap": round(worst_jump, 4) if worst_jump is not None else None,
            "worst_at": str(worst_action.ex_date) if worst_action else None,
            "verdict": (
                "continuous" if worst_jump is not None and worst_jump <= args.tolerance
                else "discontinuous" if worst_jump is not None else "no_reference"
            ),
        })

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "continuity of stored close across split ex-date (|ratio-1| <= tolerance)",
        "instruments_scanned": scanned,
        "with_split_or_bonus": len([c for c in checked if c.get("actions")]),
        "tolerance": args.tolerance,
        "results": checked,
        "summary": {
            verdict: len([c for c in checked if c.get("verdict") == verdict])
            for verdict in ("continuous", "discontinuous", "no_reference", "provider_error")
        },
    }
    write_json("corporate_actions_report.json", payload)
    print(json.dumps(payload, indent=2, default=str))
    db.close()
    return 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def cmd_report(args: argparse.Namespace) -> int:
    db = make_session()
    store = CheckpointStore(CHECKPOINT_PATH)
    run_id = args.run_id or store.latest_run()
    if run_id is None:
        print("no validation run found — run `validate` first", file=sys.stderr)
        return 2

    service = make_service(db)
    validator = LiveMarketDataValidator(
        db=db, service=service, store=store,
        timeframes=_timeframes(args.timeframes),
    )
    instruments = validator.universe()

    findings = list(store.findings(run_id))
    by_code: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for f in findings:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    failed_units = [f for f in findings if f["status"] == "failed"]
    bar_count = db.execute(select(func.count()).select_from(OHLCV)).scalar_one()
    instrument_count = db.execute(select(func.count()).select_from(Instrument)).scalar_one()

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "instrument_master": {
            "total_rows": instrument_count,
            "active_tradable": len(instruments),
        },
        "stored_bars": bar_count,
        "coverage": validator.coverage(run_id, instruments),
        "findings_by_severity": by_severity,
        "findings_by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
        "quarantine_by_reason": validator.quarantine_breakdown(),
        "failed_units_sample": failed_units[: args.max_failures],
        "failed_units_total": len(failed_units),
        "metrics": metrics.snapshot(),
    }
    path = write_json("validation_report.json", payload)
    md_path = write_markdown(payload)
    print(json.dumps(payload, indent=2, default=str))
    print(f"\nwrote {path}\nwrote {md_path}")
    db.close()
    return 0


def write_markdown(payload: dict) -> Path:
    """Render the machine-readable report into something a human will actually read."""
    discovery = {}
    disc_path = ARTIFACTS / "discovery_report.json"
    if disc_path.exists():
        discovery = json.loads(disc_path.read_text(encoding="utf-8"))

    cov = payload["coverage"]
    lines: list[str] = [
        "# Market Data Layer — Live Validation Report",
        "",
        f"Generated {payload['generated_at']} · run `{payload['run_id']}`",
        "",
        "## Instrument discovery",
        "",
    ]
    if discovery:
        d = discovery["discovery"]
        lines += [
            f"- **Total discovered:** {d['total_discovered']:,}",
            f"- **Active / tradable:** {d['active']:,}",
            f"- **Inactive:** {d['inactive']:,} (of which delisted {d['delisted']:,})",
            f"- **By exchange:** {d['by_exchange']}",
            f"- **By asset class:** {d['by_asset_class']}",
            f"- **With ISIN:** {d['with_isin']:,} · missing {d['missing_isin']:,}",
            f"- **Dual listings cross-mapped:** {d['cross_mapped_isins']:,}",
            f"- **Duplicate/ambiguity groups:** {d['duplicate_groups']}",
            f"- **Discovery time:** {d['duration_seconds']}s",
            "",
            "| Source | Exchange | Asset class | OK | Count | Seconds |",
            "|---|---|---|---|---|---|",
        ]
        for s in discovery["per_source"]:
            ok = "yes" if s["ok"] else f"**NO** — {s['error']}"
            lines.append(
                f"| `{s['source']}` | {s['exchange']} | {s['asset_class']} | {ok} "
                f"| {s['count']:,} | {s['seconds']} |"
            )
        lines += ["", f"Calendar coverage: {discovery.get('calendar_coverage')}", ""]

    lines += [
        "## Validation coverage",
        "",
        f"- **Instruments in queue:** {cov['universe_instruments']:,}",
        f"- **Timeframes:** {', '.join(cov['timeframes'])}",
        f"- **Units attempted:** {cov['units_recorded']:,} of "
        f"{cov['total_units']:,} ({cov['coverage_pct']}%)",
        f"- **Remaining:** {cov['remaining_units']:,}",
        f"- **Status breakdown:** {cov['by_status']}",
        f"- **Bars ingested:** {cov['total_bars']:,}",
        f"- **Bars quarantined:** {cov['total_quarantined']:,}",
        f"- **Missing intervals detected:** {cov['total_missing_intervals']:,}",
        f"- **Mean unit latency:** {cov['avg_unit_latency_ms']} ms",
        "",
        "### Units by timeframe",
        "",
        "| Timeframe | Units |",
        "|---|---|",
    ]
    for tf, n in sorted(cov["by_timeframe"].items()):
        lines.append(f"| {tf} | {n:,} |")

    lines += ["", "## Findings", ""]
    if payload["findings_by_severity"]:
        lines += [f"- **By severity:** {payload['findings_by_severity']}", "",
                  "| Code | Count |", "|---|---|"]
        for code, n in payload["findings_by_code"].items():
            lines.append(f"| `{code}` | {n:,} |")
    else:
        lines.append("No findings recorded.")

    lines += ["", "## Quarantine", ""]
    quarantine = payload["quarantine_by_reason"]
    if quarantine:
        lines += ["| Reason | Bars |", "|---|---|"]
        lines += [f"| `{k}` | {v:,} |" for k, v in sorted(quarantine.items())]
    else:
        lines.append("Nothing quarantined.")

    lines += [
        "", "## Failed units", "",
        f"Total failing findings: {payload['failed_units_total']:,}", "",
    ]
    if payload["failed_units_sample"]:
        lines += ["| Symbol | Exchange | Timeframe | Code | Detail |", "|---|---|---|---|---|"]
        for f in payload["failed_units_sample"][:40]:
            lines.append(
                f"| {f['symbol']} | {f['exchange']} | {f['timeframe']} "
                f"| `{f['code']}` | {f['detail']} |"
            )

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / "VALIDATION_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="discover + reconcile the instrument universe")
    p_disc.add_argument("--max-duplicates", type=int, default=50)
    p_disc.set_defaults(func=cmd_discover)

    p_val = sub.add_parser("validate", help="run a resumable validation batch")
    p_val.add_argument("--batch-size", type=int, default=200)
    p_val.add_argument("--timeframes", default="all")
    p_val.add_argument("--exchanges", default="")
    p_val.add_argument("--asset-classes", default="")
    p_val.add_argument("--limit", type=int, default=None,
                       help="cap instruments pulled from the master (ordering is stable)")
    p_val.add_argument("--pause", type=float, default=0.0,
                       help="seconds to sleep between units, for provider courtesy")
    p_val.add_argument("--retry-failed", action="store_true")
    p_val.add_argument("--run-id", default=None)
    p_val.set_defaults(func=cmd_validate)

    p_prov = sub.add_parser("providers", help="validate provider resilience behaviour")
    p_prov.add_argument("--symbol", default="RELIANCE")
    p_prov.add_argument("--health-samples", type=int, default=3)
    p_prov.set_defaults(func=cmd_providers)

    p_ca = sub.add_parser(
        "corporate-actions",
        help="validate back-adjustment against the provider's adjusted series",
    )
    p_ca.add_argument("--scan", type=int, default=120,
                      help="instruments to scan for a split/bonus in the window")
    p_ca.add_argument("--samples", type=int, default=8,
                      help="stop after this many instruments with a usable action")
    p_ca.add_argument("--lookback-days", type=int, default=1460)
    p_ca.add_argument("--tolerance", type=float, default=0.15,
                      help="max |close-ratio - 1| across an ex-date to call it continuous")
    p_ca.set_defaults(func=cmd_corporate_actions)

    p_rep = sub.add_parser("report", help="emit the consolidated validation report")
    p_rep.add_argument("--run-id", default=None)
    p_rep.add_argument("--timeframes", default="all")
    p_rep.add_argument("--max-failures", type=int, default=100)
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
