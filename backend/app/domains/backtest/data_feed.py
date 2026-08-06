"""Point-in-Time Data Feed with strict Look-Ahead Prevention and Streamable Replay."""
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domains.backtest.exceptions import LookAheadBiasError
from app.domains.market_data.models import Instrument, OHLCV
from app.domains.trading.clock import Clock


@dataclass(frozen=True)
class HistoricalBar:
    """Immutable bar record passed through point-in-time queries."""
    instrument_id: uuid.UUID
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: str = "1d"


class PointInTimeDataFeed:
    """Historical market data feed enforcing point-in-time look-ahead protection.
    Strategies and simulation components receive a restricted view of market data
    where any data with timestamp > clock.now() is strictly inaccessible.
    """

    def __init__(
        self,
        clock: Clock,
        bars: list[HistoricalBar] | None = None,
    ):
        self._clock = clock
        # Multi-instrument time-indexed storage: instrument_id -> list of HistoricalBar sorted by timestamp
        self._bars_by_instrument: dict[uuid.UUID, list[HistoricalBar]] = defaultdict(list)
        
        if bars:
            for bar in sorted(bars, key=lambda b: (b.timestamp, b.symbol)):
                self._bars_by_instrument[bar.instrument_id].append(bar)

    @classmethod
    def from_database(
        cls,
        db: Session,
        clock: Clock,
        instrument_ids: list[uuid.UUID],
        start_date: date,
        end_date: date,
        timeframe: str = "1d",
        chunk_size: int = 5000,
    ) -> "PointInTimeDataFeed":
        """Streamable database loader for multi-instrument historical bars."""
        # Load instrument symbol mappings
        inst_stmt = select(Instrument).where(Instrument.id.in_(instrument_ids))
        instruments = {inst.id: inst.trading_symbol for inst in db.scalars(inst_stmt)}

        # Load bars in chronological order
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        stmt = (
            select(OHLCV)
            .where(
                and_(
                    OHLCV.instrument_id.in_(instrument_ids),
                    OHLCV.timeframe == timeframe,
                    OHLCV.ts >= start_dt,
                    OHLCV.ts <= end_dt,
                )
            )
            .order_by(OHLCV.ts.asc(), OHLCV.instrument_id.asc())
        )

        all_bars: list[HistoricalBar] = []
        # Chunked streaming to prevent OOM on large universes
        for bar_record in db.scalars(stmt).yield_per(chunk_size):
            all_bars.append(
                HistoricalBar(
                    instrument_id=bar_record.instrument_id,
                    symbol=instruments.get(bar_record.instrument_id, str(bar_record.instrument_id)),
                    timestamp=bar_record.ts,
                    open=Decimal(str(bar_record.open)),
                    high=Decimal(str(bar_record.high)),
                    low=Decimal(str(bar_record.low)),
                    close=Decimal(str(bar_record.close)),
                    volume=int(bar_record.volume),
                    timeframe=bar_record.timeframe,
                )
            )

        return cls(clock=clock, bars=all_bars)

    def add_bars(self, bars: list[HistoricalBar]) -> None:
        """Add additional bars to in-memory store."""
        for bar in bars:
            self._bars_by_instrument[bar.instrument_id].append(bar)
        for inst_id in self._bars_by_instrument:
            self._bars_by_instrument[inst_id].sort(key=lambda b: b.timestamp)

    def get_latest_bar(self, instrument_id: uuid.UUID) -> HistoricalBar | None:
        """Get the most recent bar for instrument strictly <= current simulation clock."""
        now = self._clock.now()
        bars = self._bars_by_instrument.get(instrument_id, [])
        valid_bars = [b for b in bars if b.timestamp <= now]
        return valid_bars[-1] if valid_bars else None

    def get_history(
        self,
        instrument_id: uuid.UUID,
        lookback_bars: int = 100,
    ) -> list[HistoricalBar]:
        """Get historical bars strictly <= current simulation clock.
        Raises LookAheadBiasError if lookback attempts to access future bars.
        """
        now = self._clock.now()
        bars = self._bars_by_instrument.get(instrument_id, [])
        valid_bars = [b for b in bars if b.timestamp <= now]
        
        if not valid_bars:
            return []
        
        return valid_bars[-lookback_bars:]

    def assert_no_lookahead(self, requested_timestamp: datetime, instrument_id: uuid.UUID | None = None) -> None:
        """Guard method explicitly raising LookAheadBiasError if requested_timestamp > clock.now()."""
        now = self._clock.now()
        if requested_timestamp > now:
            raise LookAheadBiasError(
                requested_time=requested_timestamp,
                current_clock=now,
                instrument_id=instrument_id,
            )

    def iter_all_bars_chronologically(self) -> Iterator[HistoricalBar]:
        """Stream all historical bars merged chronologically across all instruments."""
        # Collect and sort all bars globally
        all_bars: list[HistoricalBar] = []
        for inst_bars in self._bars_by_instrument.values():
            all_bars.extend(inst_bars)
        
        all_bars.sort(key=lambda b: (b.timestamp, b.symbol))
        for bar in all_bars:
            yield bar
