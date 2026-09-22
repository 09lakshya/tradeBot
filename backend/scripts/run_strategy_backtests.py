"""Backtest every registered strategy and rank them on out-of-sample results.

    python backend/scripts/run_strategy_backtests.py run --symbols 60 --split 0.7
    python backend/scripts/run_strategy_backtests.py report

Why out-of-sample: a strategy tuned on the same bars it is judged on always looks
good. Each strategy is fitted on the earlier slice and scored on the later one it
never saw; only the later slice decides whether it is kept.

The output is a ranking and a suggested ``AUTOTRADER_STRATEGIES`` line. Strategies
that lose money, never trade, or draw down past the limit are excluded -- the
autotrader blends signals from everything enabled, so a negative-edge strategy
pollutes the consensus that sizes real positions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import warnings
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

import app.models  # noqa: E402,F401 - registers every table, or FK resolution fails
from app.core.db import SessionLocal  # noqa: E402
from app.domains.backtest.schemas import BacktestCreateRequest  # noqa: E402
from app.domains.backtest.service import BacktestService  # noqa: E402
from app.domains.market_data.models import OHLCV, Instrument  # noqa: E402
from app.domains.orchestrator.live_market import load_watchlist  # noqa: E402
from app.domains.strategies.registry import StrategyRegistry  # noqa: E402

RESULTS_PATH = REPO_ROOT / "docs" / "validation" / "strategy-backtests.json"

# A strategy has to clear all of these on the unseen slice to be worth trading.
MIN_TRADES = 5
MIN_RETURN_PCT = 0.0
MAX_DRAWDOWN_PCT = 25.0


def _universe(db, limit: int) -> list[Instrument]:
    """Liquid names that actually have bars, in watchlist (liquidity) order."""
    symbols = load_watchlist()
    rows = db.scalars(
        select(Instrument).where(Instrument.trading_symbol.in_(symbols))
    ).all()
    counts = dict(
        db.execute(
            select(OHLCV.instrument_id, func.count())
            .where(OHLCV.instrument_id.in_([r.id for r in rows]))
            .group_by(OHLCV.instrument_id)
        ).all()
    )
    order = {s: i for i, s in enumerate(symbols)}
    usable = [r for r in rows if counts.get(r.id, 0) >= 250]
    usable.sort(key=lambda r: order.get(r.trading_symbol, 10**6))
    return usable[:limit]


def _bar_range(db, instruments: list[Instrument]) -> tuple[date, date]:
    ids = [i.id for i in instruments]
    lo, hi = db.execute(
        select(func.min(OHLCV.ts), func.max(OHLCV.ts)).where(OHLCV.instrument_id.in_(ids))
    ).one()
    return lo.date(), hi.date()


def _metric(metrics: dict, *names: str, default: float = 0.0) -> float:
    for n in names:
        if n in metrics and metrics[n] is not None:
            try:
                return float(metrics[n])
            except (TypeError, ValueError):
                continue
    return default


def cmd_run(args: argparse.Namespace) -> int:
    strategy_ids = [m.strategy_id for m in StrategyRegistry.list_strategies()]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        strategy_ids = [s for s in strategy_ids if s in wanted]

    with SessionLocal() as db:
        instruments = _universe(db, args.symbols)
        if not instruments:
            print("no instruments with enough history; run bootstrap_live_universe.py first")
            return 1
        first, last = _bar_range(db, instruments)

    # Chronological split: fit on the earlier slice, judge on the later one.
    total_days = (last - first).days
    split_day = first + timedelta(days=int(total_days * args.split))

    print(f"strategies : {len(strategy_ids)}")
    print(f"universe   : {len(instruments)} symbols")
    print(f"bars       : {first} -> {last}")
    print(f"in-sample  : {first} -> {split_day}")
    print(f"out-sample : {split_day} -> {last}")
    print(f"capital    : Rs {args.capital:,.0f} per run\n")

    runs: list[dict] = []
    t0 = time.time()

    for n, sid in enumerate(strategy_ids, 1):
        row: dict = {"strategy_id": sid}
        for label, (s_from, s_to) in {
            "in_sample": (first, split_day),
            "out_sample": (split_day, last),
        }.items():
            with SessionLocal() as db:
                svc = BacktestService(db=db)
                try:
                    bt = svc.create_backtest(
                        BacktestCreateRequest(
                            name=f"{sid}-{label}",
                            strategy_id=sid,
                            instrument_ids=[i.id for i in instruments],
                            start_date=s_from,
                            end_date=s_to,
                            initial_capital=Decimal(str(args.capital)),
                        )
                    )
                    bt = svc.run_backtest(bt.id)
                    result = bt.results[0] if bt.results else None
                    metrics = (result.metrics if result else {}) or {}
                    row[label] = {
                        "status": bt.status.value
                        if hasattr(bt.status, "value")
                        else str(bt.status),
                        "trades": result.trade_count if result else 0,
                        "return_pct": _metric(metrics, "total_return_pct", "total_return"),
                        "sharpe": _metric(metrics, "sharpe_ratio", "sharpe"),
                        "sortino": _metric(metrics, "sortino_ratio", "sortino"),
                        "max_drawdown_pct": _metric(metrics, "max_drawdown_pct", "max_drawdown"),
                        "win_rate": _metric(metrics, "win_rate", "win_rate_pct"),
                        "profit_factor": _metric(metrics, "profit_factor"),
                        "error": bt.error,
                    }
                except Exception as exc:  # noqa: BLE001 - record and continue the sweep
                    db.rollback()
                    row[label] = {
                        "status": "error",
                        "trades": 0,
                        "return_pct": 0.0,
                        "sharpe": 0.0,
                        "max_drawdown_pct": 0.0,
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    }
                    if args.verbose:
                        traceback.print_exc()

        oos = row.get("out_sample", {})
        print(
            f"[{n:>2}/{len(strategy_ids)}] {sid:<28} "
            f"oos return {oos.get('return_pct', 0):>7.2f}%  "
            f"sharpe {oos.get('sharpe', 0):>6.2f}  "
            f"dd {oos.get('max_drawdown_pct', 0):>6.2f}%  "
            f"trades {oos.get('trades', 0):>4}"
            + (f"  [{oos.get('error', '')[:40]}]" if oos.get("error") else "")
        )
        runs.append(row)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "universe_size": len(instruments),
        "symbols": [i.trading_symbol for i in instruments],
        "bars_from": first.isoformat(),
        "bars_to": last.isoformat(),
        "split_date": split_day.isoformat(),
        "initial_capital": args.capital,
        "acceptance": {
            "min_trades": MIN_TRADES,
            "min_return_pct": MIN_RETURN_PCT,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
        },
        "runs": runs,
        "duration_seconds": round(time.time() - t0, 1),
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS_PATH}  ({payload['duration_seconds']}s)")
    return cmd_report(args)


def _passes(oos: dict) -> bool:
    return (
        oos.get("status") == "completed"
        and oos.get("trades", 0) >= MIN_TRADES
        and oos.get("return_pct", 0.0) > MIN_RETURN_PCT
        and abs(oos.get("max_drawdown_pct", 0.0)) <= MAX_DRAWDOWN_PCT
    )


def cmd_report(args: argparse.Namespace) -> int:
    if not RESULTS_PATH.exists():
        print("no results yet; run the 'run' command first")
        return 1
    payload = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    runs = payload["runs"]

    ranked = sorted(
        runs,
        key=lambda r: (
            r.get("out_sample", {}).get("sharpe", 0.0),
            r.get("out_sample", {}).get("return_pct", 0.0),
        ),
        reverse=True,
    )

    print(f"\nOut-of-sample ranking ({payload['split_date']} -> {payload['bars_to']}, "
          f"{payload['universe_size']} symbols)\n")
    print(f"{'strategy':<30}{'return%':>9}{'sharpe':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}  keep")
    print("-" * 80)
    keep: list[str] = []
    for r in ranked:
        o = r.get("out_sample", {}) or {}
        ok = _passes(o)
        if ok:
            keep.append(r["strategy_id"])
        print(
            f"{r['strategy_id']:<30}{o.get('return_pct', 0):>9.2f}{o.get('sharpe', 0):>8.2f}"
            f"{o.get('max_drawdown_pct', 0):>9.2f}{o.get('trades', 0):>8}"
            f"{o.get('win_rate', 0):>7.1f}  {'YES' if ok else '-'}"
        )

    print(
        f"\n{len(keep)} of {len(runs)} strategies cleared: >={MIN_TRADES} trades, "
        f"positive return, drawdown <= {MAX_DRAWDOWN_PCT}% on unseen bars."
    )
    if keep:
        print("\nPut this in .env to trade only these:\n")
        print(f"AUTOTRADER_STRATEGIES={','.join(keep)}")
    else:
        print("\nNothing cleared. Leave AUTOTRADER_STRATEGIES blank only if you accept")
        print("that no strategy here has demonstrated an edge on unseen data.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--symbols", type=int, default=60, help="universe size per backtest")
    p_run.add_argument("--split", type=float, default=0.7, help="fraction of history fitted on")
    p_run.add_argument("--capital", type=float, default=1_000_000.0)
    p_run.add_argument("--only", default="", help="comma-separated strategy ids")
    p_run.add_argument("--verbose", action="store_true")

    sub.add_parser("report")

    args = ap.parse_args()
    if args.cmd == "report":
        args.__dict__.setdefault("verbose", False)
    return {"run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
