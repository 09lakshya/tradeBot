"""Signal Aggregator for multi-strategy ingestion, TTL expiration filtering, and instrument partitioning."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Sequence
import uuid

from app.domains.portfolio.exceptions import IncompatibleSignalError
from app.domains.portfolio.schemas import PortfolioSnapshot
from app.domains.strategies.schemas import TradingSignal

log = logging.getLogger(__name__)


class SignalAggregator:
    """Collects, validates TTL, deduplicates, and groups strategy signals by instrument."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self.default_ttl_seconds = default_ttl_seconds

    def aggregate(
        self,
        signals: Sequence[TradingSignal],
        current_time: datetime,
        portfolio_snapshot: PortfolioSnapshot | None = None,
        min_daily_volume: Decimal | None = None,
    ) -> dict[uuid.UUID, list[TradingSignal]]:
        """Groups active, non-expired trading signals by instrument_id.

        Raises IncompatibleSignalError if any signal is timestamped in the future relative to current_time.
        """
        grouped: dict[uuid.UUID, list[TradingSignal]] = {}

        for sig in signals:
            # Ensure timezone consistency
            sig_ts = sig.timestamp if sig.timestamp.tzinfo else sig.timestamp.replace(tzinfo=timezone.utc)
            curr_ts = current_time if current_time.tzinfo else current_time.replace(tzinfo=timezone.utc)

            # Strict point-in-time check
            if sig_ts > curr_ts + timedelta(seconds=1):
                raise IncompatibleSignalError(
                    f"Look-ahead signal detected: signal timestamp {sig_ts} > current time {curr_ts}"
                )

            # Check expiration
            if sig.signal_expiry:
                expiry_ts = sig.signal_expiry if sig.signal_expiry.tzinfo else sig.signal_expiry.replace(tzinfo=timezone.utc)
                if curr_ts > expiry_ts:
                    log.debug("Discarding expired signal %s for %s", sig.signal_id, sig.symbol)
                    continue
            else:
                ttl_limit = sig_ts + timedelta(seconds=self.default_ttl_seconds)
                if curr_ts > ttl_limit:
                    log.debug("Discarding signal %s exceeding default TTL for %s", sig.signal_id, sig.symbol)
                    continue

            # Optional liquidity filter
            if min_daily_volume and portfolio_snapshot and portfolio_snapshot.historical_volumes:
                vol = portfolio_snapshot.historical_volumes.get(sig.instrument_id, Decimal("0"))
                if vol < min_daily_volume:
                    log.debug("Discarding signal %s due to low daily volume %s < %s", sig.signal_id, vol, min_daily_volume)
                    continue

            if sig.instrument_id not in grouped:
                grouped[sig.instrument_id] = []
            grouped[sig.instrument_id].append(sig)

        return grouped
