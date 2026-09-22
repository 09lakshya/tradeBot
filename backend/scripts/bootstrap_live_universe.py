"""Prepare the live paper-trading universe: instruments, liquidity screen, history.

Run from the repo root so ``.env`` resolves:

    python backend/scripts/bootstrap_live_universe.py discover   # NSE equities -> instruments
    python backend/scripts/bootstrap_live_universe.py rank       # liquidity screen -> watchlist
    python backend/scripts/bootstrap_live_universe.py history    # daily bars for the watchlist
    python backend/scripts/bootstrap_live_universe.py status

Every listed NSE equity is loaded into ``instruments``. Only the most liquid
``--top`` names become the tradable watchlist, because a cycle cannot poll
thousands of symbols within one interval, and thin names make simulated fills
meaningless -- a paper fill at the last print is a fantasy when the book is empty.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.domains.market_data.discovery.nse import NSEEquitySource  # noqa: E402
from app.domains.market_data.enums import Exchange, Timeframe  # noqa: E402
from app.domains.market_data.models import Instrument  # noqa: E402
from app.domains.market_data.providers.registry import build_router  # noqa: E402
from app.domains.market_data.schemas import OHLCVBar  # noqa: E402
from app.domains.market_data.service import MarketDataService  # noqa: E402

WATCHLIST_PATH = REPO_ROOT / "config" / "trading_universe.json"
BATCH_SIZE = 150
PROVIDER = "yahoo"


def _yf():
    import yfinance as yf

    return yf


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------------------------------------------------------------------
# discover
# --------------------------------------------------------------------------
def cmd_discover(args: argparse.Namespace) -> int:
    dtos = NSEEquitySource().fetch()
    print(f"NSE equities discovered: {len(dtos)}")

    created = 0
    with SessionLocal() as db:
        svc = MarketDataService(db=db, provider=build_router(PROVIDER))
        for i, dto in enumerate(dtos, 1):
            before = db.scalar(
                select(Instrument).where(
                    Instrument.trading_symbol == dto.trading_symbol,
                    Instrument.exchange == Exchange.NSE,
                )
            )
            svc.get_or_create_instrument(dto)
            if before is None:
                created += 1
            if i % 500 == 0:
                db.commit()
                print(f"  ...{i}/{len(dtos)}")
        db.commit()

    from sqlalchemy import func

    with SessionLocal() as db:
        total = db.scalar(
            select(func.count()).select_from(Instrument).where(Instrument.exchange == Exchange.NSE)
        )
    print(f"instruments in db (NSE): {total}  (new this run: {created})")
    return 0


# --------------------------------------------------------------------------
# rank
# --------------------------------------------------------------------------
def cmd_rank(args: argparse.Namespace) -> int:
    """Screen the universe by traded value and keep the top N."""
    yf = _yf()
    with SessionLocal() as db:
        instruments = db.scalars(
            select(Instrument).where(
                Instrument.exchange == Exchange.NSE, Instrument.is_delisted.is_(False)
            )
        ).all()
        symbols = sorted({i.trading_symbol for i in instruments})

    print(f"screening {len(symbols)} symbols for liquidity ({args.period})...")
    turnover: dict[str, float] = {}
    t0 = time.time()

    for n, batch in enumerate(_batches(symbols, BATCH_SIZE), 1):
        tickers = [f"{s}.NS" for s in batch]
        try:
            df = yf.download(
                " ".join(tickers), period=args.period, interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001 - one bad batch must not stop the screen
            print(f"  batch {n} failed: {type(exc).__name__}")
            continue

        for sym, ticker in zip(batch, tickers, strict=True):
            try:
                sub = df[ticker].dropna()
                if len(sub) < 5:
                    continue
                # Median daily traded value: robust to a single spike day.
                tv = (sub["Close"] * sub["Volume"]).median()
                if tv and tv > 0:
                    turnover[sym] = float(tv)
            except Exception:  # noqa: BLE001, S110 - symbol simply has no data
                continue
        print(f"  batch {n}: {len(turnover)} priced so far ({time.time() - t0:.0f}s)")

    ranked = sorted(turnover.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[: args.top]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "exchange": "NSE",
        "screen": {
            "metric": "median daily traded value (close x volume)",
            "period": args.period,
            "universe_screened": len(symbols),
            "priced": len(turnover),
        },
        "symbols": [s for s, _ in top],
        "turnover": {s: round(v, 2) for s, v in top},
    }
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\npriced {len(turnover)} of {len(symbols)}; wrote top {len(top)} to {WATCHLIST_PATH}")
    for s, v in top[:10]:
        print(f"   {s:<14} median daily turnover Rs {v / 1e7:,.1f} cr")
    return 0


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------
def cmd_history(args: argparse.Namespace) -> int:
    """Load daily bars for the watchlist. Strategies need lookback to emit anything."""
    yf = _yf()
    payload = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    symbols = payload["symbols"]
    print(f"loading {args.period} of daily bars for {len(symbols)} symbols...")

    total_bars = 0
    t0 = time.time()
    with SessionLocal() as db:
        svc = MarketDataService(db=db, provider=build_router(PROVIDER))
        lookup = {
            i.trading_symbol: i
            for i in db.scalars(
                select(Instrument).where(Instrument.trading_symbol.in_(symbols))
            ).all()
        }

        for n, batch in enumerate(_batches(symbols, BATCH_SIZE), 1):
            tickers = [f"{s}.NS" for s in batch]
            try:
                df = yf.download(
                    " ".join(tickers), period=args.period, interval="1d",
                    group_by="ticker", threads=True, progress=False, auto_adjust=False,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  batch {n} failed: {type(exc).__name__}")
                continue

            for sym, ticker in zip(batch, tickers, strict=True):
                inst = lookup.get(sym)
                if inst is None:
                    continue
                try:
                    sub = df[ticker].dropna()
                except Exception:  # noqa: BLE001
                    continue
                bars = []
                for ts, row in sub.iterrows():
                    stamp = ts.to_pydatetime()
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=UTC)
                    bars.append(
                        OHLCVBar(
                            ts=stamp,
                            open=float(row["Open"]), high=float(row["High"]),
                            low=float(row["Low"]), close=float(row["Close"]),
                            adjusted_close=float(row.get("Adj Close", row["Close"])),
                            volume=int(row["Volume"] or 0),
                        )
                    )
                if bars:
                    total_bars += svc._upsert_bars(inst.id, Timeframe.d1, bars, PROVIDER)
            print(f"  batch {n}: {total_bars} bars stored ({time.time() - t0:.0f}s)")

    print(f"\nstored {total_bars} daily bars")
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def cmd_status(args: argparse.Namespace) -> int:
    from sqlalchemy import func

    from app.domains.market_data.models import OHLCV

    with SessionLocal() as db:
        n_inst = db.scalar(select(func.count()).select_from(Instrument))
        n_bars = db.scalar(select(func.count()).select_from(OHLCV))
    wl = (
        json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))["symbols"]
        if WATCHLIST_PATH.exists()
        else []
    )
    print(f"instruments : {n_inst}")
    print(f"watchlist   : {len(wl)} symbols ({WATCHLIST_PATH if wl else 'not built'})")
    print(f"daily bars  : {n_bars}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover")

    p_rank = sub.add_parser("rank")
    p_rank.add_argument("--top", type=int, default=500)
    p_rank.add_argument("--period", default="3mo")

    p_hist = sub.add_parser("history")
    p_hist.add_argument("--period", default="2y")

    sub.add_parser("status")

    args = ap.parse_args()
    return {
        "discover": cmd_discover,
        "rank": cmd_rank,
        "history": cmd_history,
        "status": cmd_status,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
