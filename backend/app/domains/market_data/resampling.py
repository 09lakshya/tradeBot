"""Timeframe derivation.

No vendor serves every timeframe the platform supports — Yahoo, for instance, has
no 4h interval, and Indian exchanges have no natural 4h boundary anyway (the
equity session is 6h15m). Rather than let coverage depend on vendor menus, higher
timeframes are aggregated from a finer one that the provider *does* serve.

Aggregation is session-anchored: buckets start at each trading day's first bar
rather than at a fixed wall-clock grid. A midnight-anchored 4h grid would split
the 09:15–15:30 session at 12:00 and produce two ragged bars whose boundaries
mean nothing to a strategy.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domains.market_data.enums import Timeframe
from app.domains.market_data.schemas import OHLCVBar

#: Timeframes that must be derived, mapped to the finest source that composes
#: them exactly. Only whole-multiple relationships are allowed — deriving 4h from
#: 30m and from 1h give the same answer, so prefer the fewest source bars.
DERIVED_FROM: dict[Timeframe, Timeframe] = {
    Timeframe.h4: Timeframe.h1,
}


class ResamplingError(ValueError):
    """The requested derivation is not a valid aggregation."""


def can_derive(target: Timeframe, source: Timeframe) -> bool:
    """True when ``target`` is a whole multiple of ``source``."""
    if target.seconds <= source.seconds:
        return False
    return target.seconds % source.seconds == 0


def resample(
    bars: list[OHLCVBar],
    source: Timeframe,
    target: Timeframe,
    session_timezone: ZoneInfo,
) -> list[OHLCVBar]:
    """Aggregate ``bars`` from ``source`` into ``target`` bars.

    Buckets restart every session day in ``session_timezone``, so a partial final
    bucket (the tail of a 6h15m session under a 4h frame) is emitted as a short
    bar rather than being merged into the next day.
    """
    if not can_derive(target, source):
        raise ResamplingError(
            f"cannot derive {target.value} from {source.value}: not a whole multiple"
        )
    if not bars:
        return []

    span = target.seconds // source.seconds
    ordered = sorted(bars, key=lambda b: b.ts)

    out: list[OHLCVBar] = []
    bucket: list[OHLCVBar] = []
    bucket_day: datetime | None = None

    for bar in ordered:
        local_day = bar.ts.astimezone(session_timezone).date()
        # `bucket` is empty whenever the previous bar completed a full span, so the
        # day-boundary flush must tolerate that rather than fold an empty list.
        if bucket and local_day != bucket_day:
            out.append(_fold(bucket))
            bucket = []
        bucket_day = local_day
        bucket.append(bar)
        if len(bucket) == span:
            out.append(_fold(bucket))
            bucket = []
    if bucket:
        out.append(_fold(bucket))
    return out


def _fold(bucket: list[OHLCVBar]) -> OHLCVBar:
    """Collapse consecutive bars into one. Timestamp = bucket open (left-labelled)."""
    return OHLCVBar(
        ts=bucket[0].ts,
        open=bucket[0].open,
        high=max(b.high for b in bucket),
        low=min(b.low for b in bucket),
        close=bucket[-1].close,
        volume=sum(b.volume for b in bucket),
        adjusted_close=bucket[-1].adjusted_close,
    )
