"""Live market inputs for the execution pipeline: real prices and real signals.

The pipeline was built as a harness. Stage 2 defaults every instrument to a
placeholder price and stage 3 only forwards ``provided_signals`` -- so nothing
connected the strategy library to market data. This module is that connection:

* :class:`LivePriceFeed`   -- batch quotes for the tradable watchlist.
* :class:`LiveSignalEngine` -- runs registered strategies over stored bars and
  returns the signals the pipeline consumes.

Both read the watchlist written by ``scripts/bootstrap_live_universe.py``. Every
listed equity lives in ``instruments``; only the liquid screen is polled, because
a cycle cannot fetch thousands of quotes inside its interval.
"""
from __future__ import annotations

import json
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.backtest.data_feed import PointInTimeDataFeed
from app.domains.market_data.models import Instrument
from app.domains.market_data.providers.registry import build_router as _build_router
from app.domains.strategies.base import StrategyContext
from app.domains.strategies.registry import StrategyRegistry
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import Clock, SystemClock
from app.domains.trading.models import Portfolio, Position

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
WATCHLIST_PATH = REPO_ROOT / "config" / "trading_universe.json"

# Yahoo serves Indian intraday on a delay; a batch this size answers well inside
# a cycle interval. Raising it risks throttling, which costs the whole cycle.
QUOTE_BATCH = 100


def load_watchlist() -> list[str]:
    """Trading symbols the autotrader is allowed to act on."""
    if not WATCHLIST_PATH.exists():
        return []
    payload = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    return list(payload.get("symbols", []))


def watchlist_instruments(db: Session) -> list[Instrument]:
    symbols = load_watchlist()
    if not symbols:
        return []
    rows = db.scalars(
        select(Instrument).where(
            Instrument.trading_symbol.in_(symbols), Instrument.is_delisted.is_(False)
        )
    ).all()
    order = {s: i for i, s in enumerate(symbols)}
    return sorted(rows, key=lambda r: order.get(r.trading_symbol, 1_000_000))


class LivePriceFeed:
    """Latest traded price per instrument, fetched in batches."""

    def __init__(self, suffix: str = ".NS") -> None:
        self._suffix = suffix

    def fetch(self, instruments: list[Instrument]) -> dict[uuid.UUID, Decimal]:
        """Best-effort quotes. A symbol without a price is simply omitted, so the
        caller can skip it rather than trade on a fabricated number."""
        if not instruments:
            return {}

        warnings.filterwarnings("ignore")
        import yfinance as yf

        prices: dict[uuid.UUID, Decimal] = {}
        for start in range(0, len(instruments), QUOTE_BATCH):
            chunk = instruments[start : start + QUOTE_BATCH]
            tickers = [f"{i.trading_symbol}{self._suffix}" for i in chunk]
            try:
                df = yf.download(
                    " ".join(tickers), period="1d", interval="1m",
                    group_by="ticker", threads=True, progress=False, auto_adjust=False,
                )
            except Exception as exc:  # noqa: BLE001 - a dead batch must not kill the cycle
                log.warning("quote_batch_failed", error=str(exc), count=len(chunk))
                continue

            for inst, ticker in zip(chunk, tickers, strict=True):
                try:
                    series = df[ticker]["Close"].dropna()
                    if len(series):
                        prices[inst.id] = Decimal(str(round(float(series.iloc[-1]), 4)))
                except Exception:  # noqa: BLE001, S112 - symbol had no print
                    continue

        log.info("live_prices_fetched", requested=len(instruments), priced=len(prices))
        return prices


def refresh_daily_bars(
    db: Session,
    instruments: list[Instrument],
    period: str = "5d",
    provider: str = "yahoo",
    batch: int = 150,
) -> int:
    """Top up stored daily bars for the watchlist.

    Strategies read bars from the database, so without this the newest bar stays
    frozen at whatever the last bootstrap loaded: every cycle would re-evaluate
    the same stale history and the signals would quietly stop meaning anything.
    A short period is enough -- the upsert is keyed on (instrument, timeframe,
    ts), so re-fetching the last few sessions just refreshes them.
    """
    if not instruments:
        return 0

    warnings.filterwarnings("ignore")
    import yfinance as yf

    from app.domains.market_data.enums import Timeframe
    from app.domains.market_data.schemas import OHLCVBar
    from app.domains.market_data.service import MarketDataService

    svc = MarketDataService(db=db, provider=_build_router(provider))
    stored = 0

    for start in range(0, len(instruments), batch):
        chunk = instruments[start : start + batch]
        tickers = [f"{i.trading_symbol}.NS" for i in chunk]
        try:
            df = yf.download(
                " ".join(tickers), period=period, interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001 - a failed batch must not stop the cycle
            log.warning("bar_refresh_batch_failed", error=str(exc), count=len(chunk))
            continue

        for inst, ticker in zip(chunk, tickers, strict=True):
            try:
                sub = df[ticker].dropna()
            except Exception:  # noqa: BLE001, S112
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
                try:
                    stored += svc._upsert_bars(inst.id, Timeframe.d1, bars, provider)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "bar_refresh_store_failed",
                        symbol=inst.trading_symbol, error=str(exc),
                    )

    log.info("daily_bars_refreshed", instruments=len(instruments), bars=stored)
    return stored


class LiveSignalEngine:
    """Runs the strategy library over stored bars and collects its signals."""

    def __init__(self, clock: Clock | None = None, lookback_days: int = 400) -> None:
        self._clock = clock or SystemClock()
        self._lookback_days = lookback_days

    def _portfolio_context(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        feed: PointInTimeDataFeed,
        now: datetime,
        prices: dict[uuid.UUID, Decimal],
    ) -> StrategyContext:
        portfolio = db.get(Portfolio, portfolio_id)
        cash = portfolio.cash_balance if portfolio else Decimal("0")
        positions = {
            p.instrument_id: p.quantity
            for p in db.scalars(
                select(Position).where(Position.portfolio_id == portfolio_id)
            ).all()
        }
        invested = sum(
            (qty * prices.get(iid, Decimal("0")) for iid, qty in positions.items()),
            Decimal("0"),
        )
        return StrategyContext(
            portfolio_id=portfolio_id,
            current_time=now,
            cash_balance=cash,
            current_equity=cash + invested,
            positions=positions,
            data_feed=feed,
        )

    def generate(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        instruments: list[Instrument],
        strategy_ids: list[str],
        prices: dict[uuid.UUID, Decimal] | None = None,
        params: dict[str, dict[str, Any]] | None = None,
    ) -> list[TradingSignal]:
        """Evaluate each strategy against each instrument's most recent bar."""
        if not instruments or not strategy_ids:
            return []

        now = self._clock.now()
        prices = prices or {}
        instrument_ids = [i.id for i in instruments]
        end = now.date()
        start = end - timedelta(days=self._lookback_days)

        feed = PointInTimeDataFeed.from_database(
            db=db, clock=self._clock, instrument_ids=instrument_ids,
            start_date=start, end_date=end, timeframe="1d",
        )
        context = self._portfolio_context(db, portfolio_id, feed, now, prices)

        signals: list[TradingSignal] = []
        for strategy_id in strategy_ids:
            try:
                strategy = StrategyRegistry.create_instance(
                    strategy_id, params=(params or {}).get(strategy_id)
                )
            except Exception as exc:  # noqa: BLE001 - one bad strategy must not stop the rest
                log.warning("strategy_init_failed", strategy_id=strategy_id, error=str(exc))
                continue

            lookback = max(int(getattr(strategy, "required_lookback", 50)), 2)
            emitted = 0
            for inst in instruments:
                history = feed.get_history(inst.id, lookback_bars=lookback + 1)
                # Too little history is not a signal of anything; skip quietly.
                if len(history) <= lookback:
                    continue
                latest = history[-1]
                try:
                    strategy.initialize(context)
                    produced = strategy.on_bar(latest, context) or []
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "strategy_eval_failed",
                        strategy_id=strategy_id, symbol=inst.trading_symbol, error=str(exc),
                    )
                    continue
                signals.extend(produced)
                emitted += len(produced)

            if emitted:
                log.info("strategy_signals", strategy_id=strategy_id, signals=emitted)

        log.info(
            "signal_generation_complete",
            strategies=len(strategy_ids), instruments=len(instruments), signals=len(signals),
        )
        return signals


__all__ = [
    "LivePriceFeed",
    "refresh_daily_bars",
    "LiveSignalEngine",
    "load_watchlist",
    "watchlist_instruments",
]
