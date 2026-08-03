"""MarketDataService — orchestrates the ingestion pipeline and read paths.

Pipeline: provider (routed + resilient) -> data-quality validation -> quarantine
rejects -> corporate-action adjustment -> upsert into ohlcv -> metrics.

The service is the only writer of market data, which keeps providers as pure
adapters and lets us swap them without touching persistence.
"""
import time as _time
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.market_data.cache import MarketCache
from app.domains.market_data.calendar import MarketCalendarService
from app.domains.market_data.corporate_actions import CorporateActionEngine
from app.domains.market_data.enums import Exchange, Timeframe
from app.domains.market_data.models import (
    OHLCV,
    CorporateAction,
    Instrument,
    QuarantinedData,
)
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics
from app.domains.market_data.providers.base import MarketDataProvider
from app.domains.market_data.schemas import CorporateActionDTO, InstrumentDTO, OHLCVBar
from app.domains.market_data.sessions import exchange_timezone
from app.domains.market_data.validation import DataQualityValidator

log = get_logger(__name__)


def _as_utc(ts: datetime) -> datetime:
    """Normalize a DB timestamp to timezone-aware UTC.

    Postgres ``TIMESTAMPTZ`` returns aware datetimes, but not every driver or
    backend does. Bars must always carry a timezone, so attach UTC when absent
    rather than letting a naive value escape into the domain.
    """
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


class MarketDataService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        cache: MarketCache | None = None,
        metrics: MetricsCollector | None = None,
        calendar: MarketCalendarService | None = None,
    ) -> None:
        self._db = db
        self._provider = provider
        self._cache = cache or MarketCache()
        self._metrics = metrics or default_metrics
        self._calendar = calendar or MarketCalendarService(db, self._cache)
        self._corp = CorporateActionEngine()

    # --- instruments ----------------------------------------------------
    def get_or_create_instrument(self, dto: InstrumentDTO) -> Instrument:
        stmt = select(Instrument).where(
            Instrument.trading_symbol == dto.trading_symbol,
            Instrument.exchange == dto.exchange,
        )
        existing = self._db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing
        instrument = Instrument(
            trading_symbol=dto.trading_symbol, name=dto.name, exchange=dto.exchange,
            asset_class=dto.asset_class, instrument_type=dto.instrument_type,
            isin=dto.isin, nse_symbol=dto.nse_symbol, bse_symbol=dto.bse_symbol,
            sector=dto.sector, industry=dto.industry, lot_size=dto.lot_size,
            tick_size=dto.tick_size, currency=dto.currency, listing_date=dto.listing_date,
        )
        self._db.add(instrument)
        self._db.commit()
        self._db.refresh(instrument)
        return instrument

    def sync_instruments(self, exchange: Exchange) -> int:
        dtos = self._provider.fetch_instruments(exchange)
        for dto in dtos:
            self.get_or_create_instrument(dto)
        self._cache.invalidate("active_instruments", exchange.value)
        self._metrics.incr("instruments_synced", value=len(dtos), exchange=exchange.value)
        return len(dtos)

    def resolve_instrument(self, symbol: str, exchange: Exchange) -> Instrument | None:
        stmt = select(Instrument).where(
            Instrument.trading_symbol == symbol, Instrument.exchange == exchange
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def active_instruments(self, exchange: Exchange) -> list[Instrument]:
        stmt = select(Instrument).where(
            Instrument.exchange == exchange,
            Instrument.is_active.is_(True),
            Instrument.is_delisted.is_(False),
        )
        return list(self._db.execute(stmt).scalars())

    # --- corporate actions ----------------------------------------------
    def sync_corporate_actions(self, symbol: str, exchange: Exchange) -> int:
        instrument = self.resolve_instrument(symbol, exchange)
        if instrument is None:
            return 0
        actions = self._provider.fetch_corporate_actions(symbol, exchange)
        created = 0
        for dto in actions:
            exists = self._db.execute(
                select(CorporateAction).where(
                    CorporateAction.instrument_id == instrument.id,
                    CorporateAction.action_type == dto.action_type,
                    CorporateAction.ex_date == dto.ex_date,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            self._db.add(CorporateAction(
                instrument_id=instrument.id, action_type=dto.action_type,
                ex_date=dto.ex_date, record_date=dto.record_date,
                ratio_from=dto.ratio_from, ratio_to=dto.ratio_to,
                amount=dto.amount, new_symbol=dto.new_symbol, details=dto.details,
            ))
            created += 1
        self._db.commit()
        self._metrics.incr("corporate_actions_synced", value=created)
        return created

    def load_corporate_actions(self, instrument_id: object) -> list[CorporateActionDTO]:
        rows = self._db.execute(
            select(CorporateAction).where(CorporateAction.instrument_id == instrument_id)
        ).scalars()
        return [
            CorporateActionDTO(
                action_type=r.action_type, ex_date=r.ex_date, record_date=r.record_date,
                ratio_from=float(r.ratio_from) if r.ratio_from else None,
                ratio_to=float(r.ratio_to) if r.ratio_to else None,
                amount=float(r.amount) if r.amount else None,
                new_symbol=r.new_symbol, details=r.details,
            )
            for r in rows
        ]

    # --- OHLCV ingestion -------------------------------------------------
    def sync_ohlcv(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        start: date,
        end: date,
        adjust: bool = True,
    ) -> dict[str, int]:
        """Fetch, validate, adjust, and persist bars. Returns a per-run summary."""
        started = _time.perf_counter()
        instrument = self.resolve_instrument(symbol, exchange)
        if instrument is None:
            raise ValueError(f"unknown instrument {symbol} on {exchange.value}")

        # Pass the instrument's asset class through: symbol conventions differ by
        # class at every vendor, and a wrong mapping returns another instrument's
        # prices rather than an error.
        response = self._provider.fetch_ohlcv(
            symbol, exchange, timeframe, start, end, instrument.asset_class
        )

        validator = DataQualityValidator(
            is_known_closure=self._calendar.known_closure_checker(exchange),
            metrics=self._metrics,
            session_timezone=exchange_timezone(exchange),
        )
        result = validator.validate(response.bars, timeframe)

        # Quarantine anything that failed — never let it reach ohlcv.
        for item in result.quarantined:
            self._db.add(QuarantinedData(
                instrument_id=instrument.id, provider=response.provider,
                timeframe=timeframe, reason=item.reason,
                detail=item.detail[:500], raw_payload=item.payload,
            ))
        if result.quarantined:
            self._db.commit()

        bars = result.valid
        if adjust and bars:
            # Only apply actions the provider has NOT already folded in. Yahoo
            # pre-adjusts splits/bonuses into its Close; re-applying them here
            # would double-adjust and corrupt every pre-event price — a silent
            # data-leakage bug that poisons every backtest built on the series.
            actions = [
                a for a in self.load_corporate_actions(instrument.id)
                if a.action_type not in response.pre_adjusted
            ]
            if actions:
                bars = self._corp.adjust(bars, actions)

        inserted = self._upsert_bars(instrument.id, timeframe, bars, response.provider)

        duration = _time.perf_counter() - started
        self._metrics.observe_latency("sync_duration", duration * 1000,
                                      exchange=exchange.value, timeframe=timeframe.value)
        self._metrics.incr("db_inserts", value=inserted)
        if bars:
            freshness = (datetime.now(UTC) - max(b.ts for b in bars)).total_seconds()
            self._metrics.gauge("data_freshness_seconds", freshness, symbol=symbol)

        self._cache.invalidate("recent_ohlcv", symbol, exchange.value, timeframe.value)
        self._cache.invalidate("latest_price", symbol, exchange.value)

        summary = {
            "fetched": len(response.bars),
            "valid": len(result.valid),
            "quarantined": result.rejected_count,
            "missing_intervals": result.missing_intervals,
            "inserted": inserted,
        }
        log.info("ohlcv_synced", symbol=symbol, exchange=exchange.value,
                 timeframe=timeframe.value, **summary)
        return summary

    def _upsert_bars(
        self, instrument_id: object, timeframe: Timeframe,
        bars: list[OHLCVBar], provider: str,
    ) -> int:
        if not bars:
            return 0
        rows = [
            {
                # Persist the instant in UTC. Postgres TIMESTAMPTZ normalizes to UTC
                # anyway, but SQLite stores the wall-clock string and drops the
                # offset — writing an IST-stamped bar there and reading it back as
                # UTC would silently shift every timestamp by 5h30m.
                "instrument_id": instrument_id, "timeframe": timeframe,
                "ts": b.ts.astimezone(UTC),
                "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                "adjusted_close": b.adjusted_close, "volume": b.volume, "provider": provider,
            }
            for b in bars
        ]
        # Postgres is the production target, but the same ingestion path has to run
        # against SQLite for local validation and tests. Both dialects support
        # ON CONFLICT DO UPDATE with identical semantics; only the import differs.
        insert = pg_insert if self._db.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = insert(OHLCV).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timeframe", "ts"],
            set_={
                "open": stmt.excluded.open, "high": stmt.excluded.high,
                "low": stmt.excluded.low, "close": stmt.excluded.close,
                "adjusted_close": stmt.excluded.adjusted_close,
                "volume": stmt.excluded.volume, "provider": stmt.excluded.provider,
            },
        )
        self._db.execute(stmt)
        self._db.commit()
        return len(rows)

    # --- OHLCV reads -----------------------------------------------------
    def get_ohlcv(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe,
        start: date, end: date,
    ) -> list[OHLCVBar]:
        instrument = self.resolve_instrument(symbol, exchange)
        if instrument is None:
            return []
        # `start`/`end` are exchange-local calendar dates. Framing the window in
        # UTC would cut off the first session, because an IST trading day opens
        # at 18:30 UTC on the preceding date.
        tz = exchange_timezone(exchange)
        lower = datetime(start.year, start.month, start.day, tzinfo=tz)
        upper = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=tz)
        stmt = (
            select(OHLCV)
            .where(
                OHLCV.instrument_id == instrument.id,
                OHLCV.timeframe == timeframe,
                OHLCV.ts >= lower,
                OHLCV.ts <= upper,
            )
            .order_by(OHLCV.ts)
        )
        return [
            OHLCVBar(
                ts=_as_utc(r.ts), open=float(r.open), high=float(r.high),
                low=float(r.low), close=float(r.close), volume=r.volume,
                adjusted_close=float(r.adjusted_close) if r.adjusted_close else None,
            )
            for r in self._db.execute(stmt).scalars()
        ]

    def get_latest_price(self, symbol: str, exchange: Exchange) -> float | None:
        cached = self._cache.get("latest_price", symbol, exchange.value)
        if cached is not None:
            return float(cached)
        instrument = self.resolve_instrument(symbol, exchange)
        if instrument is None:
            return None
        stmt = (
            select(OHLCV.close)
            .where(OHLCV.instrument_id == instrument.id)
            .order_by(OHLCV.ts.desc())
            .limit(1)
        )
        row = self._db.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        price = float(row)
        self._cache.set("latest_price", price, symbol, exchange.value)
        return price
