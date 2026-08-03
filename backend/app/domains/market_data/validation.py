"""Data quality validation. Nothing corrupt reaches the ``ohlcv`` table.

Each bar is checked; failures are separated into a quarantine list (with a typed
reason and the offending payload) while clean bars pass through. Gap/missing-candle
detection is reported as a metric and does not by itself reject good bars.
"""
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domains.market_data.enums import QuarantineReason, Timeframe
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics
from app.domains.market_data.schemas import OHLCVBar
from app.domains.market_data.sessions import IST

#: Timeframes whose timestamp denotes an actual trading session, so a bar dated to
#: a market closure is a genuine defect. Weekly/monthly bars are period labels and
#: are deliberately excluded.
CALENDAR_CHECKED = frozenset({Timeframe.d1})


@dataclass
class QuarantineItem:
    reason: QuarantineReason
    detail: str
    payload: dict


@dataclass
class ValidationResult:
    valid: list[OHLCVBar] = field(default_factory=list)
    quarantined: list[QuarantineItem] = field(default_factory=list)
    missing_intervals: int = 0

    @property
    def rejected_count(self) -> int:
        return len(self.quarantined)


class DataQualityValidator:
    """Stateless validator; inject an ``is_known_closure`` callable for calendar checks.

    The predicate is deliberately "provably closed" rather than "not open".
    Quarantine is destructive — a bar rejected here never reaches ``ohlcv`` — so
    the burden of proof sits with the rejection. Where the calendar has no
    authoritative coverage the bar is kept, and the gap is a reporting problem
    rather than a data-loss one.
    """

    def __init__(
        self,
        is_known_closure: Callable[[date], bool] | None = None,
        metrics: MetricsCollector | None = None,
        session_timezone: ZoneInfo = IST,
    ) -> None:
        self._is_known_closure = is_known_closure
        self._metrics = metrics or default_metrics
        self._tz = session_timezone

    def validate(self, bars: list[OHLCVBar], timeframe: Timeframe) -> ValidationResult:
        result = ValidationResult()
        seen_ts: set[datetime] = set()
        prev_ts: datetime | None = None

        for bar in bars:
            payload = bar.model_dump(mode="json")

            # Timestamp present + timezone-aware (schema enforces tz, guard anyway).
            if bar.ts is None:
                self._reject(result, QuarantineReason.missing_timestamp, "null timestamp", payload)
                continue
            if bar.ts.tzinfo is None:
                self._reject(result, QuarantineReason.timezone_mismatch, "naive timestamp", payload)
                continue

            # Duplicate candle.
            if bar.ts in seen_ts:
                self._reject(result, QuarantineReason.duplicate, f"duplicate ts {bar.ts}", payload)
                continue

            # NaN/inf must be caught explicitly. Every comparison against NaN is
            # False, so a NaN bar slips through the OHLC relationship checks below
            # and lands in the database, where it silently poisons every indicator,
            # return, and P&L figure computed over it.
            prices = (bar.open, bar.high, bar.low, bar.close)
            if not all(math.isfinite(p) for p in prices):
                self._reject(result, QuarantineReason.corrupted,
                             "non-finite price (NaN or infinity)", payload)
                continue

            # Prices strictly positive.
            if min(prices) <= 0:
                self._reject(result, QuarantineReason.negative_price, "non-positive price", payload)
                continue

            # OHLC relationships must hold.
            if not (bar.high >= max(bar.open, bar.close) and bar.low <= min(bar.open, bar.close)
                    and bar.high >= bar.low):
                self._reject(result, QuarantineReason.invalid_ohlc,
                             "high/low inconsistent with open/close", payload)
                continue

            # Volume non-negative.
            if bar.volume < 0:
                self._reject(result, QuarantineReason.invalid_volume, "negative volume", payload)
                continue

            # Calendar consistency: reject only daily bars dated to a provable
            # closure. Weekly and monthly bars carry a *period label* — Yahoo
            # stamps a monthly bar with the 1st of the month, which is a Sunday
            # roughly a sixth of the time — so the trading-day test is meaningless
            # for them and rejecting on it would destroy legitimate history.
            local_date = bar.ts.astimezone(self._tz).date()
            if (self._is_known_closure is not None and timeframe in CALENDAR_CHECKED
                    and self._is_known_closure(local_date)):
                self._reject(result, QuarantineReason.calendar_mismatch,
                             f"bar on non-trading day {local_date}", payload)
                continue

            # Gap detection (report only). Confined to a single session: the
            # overnight and weekend gaps between sessions are not missing candles,
            # and counting them makes the metric orders of magnitude too large.
            if prev_ts is not None and timeframe.is_intraday:
                same_session = prev_ts.astimezone(self._tz).date() == local_date
                gap = (bar.ts - prev_ts).total_seconds()
                if same_session and gap > timeframe.seconds * 1.5:
                    result.missing_intervals += int(gap // timeframe.seconds) - 1

            seen_ts.add(bar.ts)
            prev_ts = bar.ts
            result.valid.append(bar)

        if result.missing_intervals:
            self._metrics.incr("missing_candles", value=result.missing_intervals)
        if result.rejected_count:
            self._metrics.incr("quarantined_bars", value=result.rejected_count)
        return result

    def _reject(
        self, result: ValidationResult, reason: QuarantineReason, detail: str, payload: dict
    ) -> None:
        result.quarantined.append(QuarantineItem(reason=reason, detail=detail, payload=payload))
