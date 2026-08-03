"""Universe discovery + Instrument Master reconciliation.

Discovery is deliberately a two-phase operation:

1. **Collect** every source into a merged, deduplicated, ISIN-cross-mapped view
   of the market — pure computation, no database involved, so it is testable
   without a DB and inspectable before anything is written.
2. **Reconcile** that view against the Instrument Master, creating, updating,
   and retiring rows.

Phase 2 refuses to retire anything for an exchange whose sources failed. A feed
outage must never be mistaken for the market delisting itself.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.market_data.discovery.base import InstrumentSource, SourceResult
from app.domains.market_data.discovery.registry import build_sources
from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics
from app.domains.market_data.schemas import InstrumentDTO

log = get_logger(__name__)

#: Instrument key as stored: the exchange plus its canonical trading symbol.
InstrumentKey = tuple[Exchange, str]


@dataclass
class DuplicateGroup:
    """Instruments that collide on an identity that should be unique."""

    kind: str                      # "symbol" | "isin"
    identity: str
    exchange: Exchange | None
    members: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class UniverseReport:
    """Everything phase 1 learned about the market."""

    results: list[SourceResult] = field(default_factory=list)
    instruments: list[InstrumentDTO] = field(default_factory=list)
    duplicates: list[DuplicateGroup] = field(default_factory=list)
    cross_mapped: int = 0
    missing_isin: int = 0
    duration_seconds: float = 0.0

    @property
    def failed_sources(self) -> list[SourceResult]:
        return [r for r in self.results if not r.ok]

    @property
    def healthy_exchanges(self) -> set[Exchange]:
        """Exchanges whose every source succeeded — the only ones safe to retire from."""
        by_exchange: dict[Exchange, list[SourceResult]] = defaultdict(list)
        for result in self.results:
            by_exchange[result.exchange].append(result)
        return {
            exchange for exchange, results in by_exchange.items()
            if all(r.ok for r in results)
        }

    def counts_by_asset_class(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for dto in self.instruments:
            counts[dto.asset_class.value] += 1
        return dict(counts)

    def counts_by_exchange(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for dto in self.instruments:
            counts[dto.exchange.value] += 1
        return dict(counts)

    def summary(self) -> dict[str, object]:
        return {
            "total_discovered": len(self.instruments),
            "active": sum(1 for i in self.instruments if i.is_active),
            "inactive": sum(1 for i in self.instruments if not i.is_active),
            "delisted": sum(1 for i in self.instruments if i.is_delisted),
            "by_exchange": self.counts_by_exchange(),
            "by_asset_class": self.counts_by_asset_class(),
            "with_isin": len(self.instruments) - self.missing_isin,
            "missing_isin": self.missing_isin,
            "cross_mapped_isins": self.cross_mapped,
            "duplicate_groups": len(self.duplicates),
            "sources_ok": [r.source for r in self.results if r.ok],
            "sources_failed": {r.source: r.error for r in self.failed_sources},
            "duration_seconds": round(self.duration_seconds, 2),
        }


@dataclass
class ReconciliationReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    reactivated: int = 0
    delisted: int = 0
    skipped_exchanges: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def summary(self) -> dict[str, object]:
        return {
            "created": self.created, "updated": self.updated,
            "unchanged": self.unchanged, "deactivated": self.deactivated,
            "reactivated": self.reactivated, "delisted": self.delisted,
            "retirement_skipped_for": self.skipped_exchanges,
            "duration_seconds": round(self.duration_seconds, 2),
        }


#: Fields reconciliation refreshes from discovery on every run.
_SYNCED_FIELDS = (
    "name", "isin", "nse_symbol", "bse_symbol", "exchange_token", "asset_class",
    "instrument_type", "industry", "lot_size", "listing_date", "currency",
    "is_active", "is_delisted",
)


class InstrumentUniverseService:
    """Discovers the tradable universe and reconciles it into the Instrument Master."""

    def __init__(
        self,
        db: Session | None = None,
        sources: list[InstrumentSource] | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._db = db
        self._sources = sources
        self._metrics = metrics or default_metrics

    # --- phase 1: discovery ---------------------------------------------
    def discover(
        self,
        exchanges: set[Exchange] | None = None,
        asset_classes: set[AssetClass] | None = None,
    ) -> UniverseReport:
        started = time.perf_counter()
        sources = self._sources or build_sources(
            exchanges=exchanges, asset_classes=asset_classes
        )
        results = [source.collect() for source in sources]

        report = UniverseReport(results=results)
        merged = self._merge(results, report)
        self._cross_map_isins(merged, report)
        report.instruments = list(merged.values())
        report.missing_isin = sum(
            1 for i in report.instruments
            if not i.isin and i.asset_class is not AssetClass.index
        )
        report.duration_seconds = time.perf_counter() - started

        for result in results:
            self._metrics.gauge(
                "discovery_source_count", float(result.count), source=result.source
            )
            self._metrics.gauge(
                "discovery_source_available", 1.0 if result.ok else 0.0, source=result.source
            )
        self._metrics.gauge("universe_size", float(len(report.instruments)))
        log.info("universe_discovered", **{
            k: v for k, v in report.summary().items() if k != "sources_failed"
        })
        return report

    def _merge(
        self, results: list[SourceResult], report: UniverseReport
    ) -> dict[InstrumentKey, InstrumentDTO]:
        """Collapse all sources into one row per (exchange, trading_symbol).

        Later sources do not blindly overwrite earlier ones: a delisted/suspended
        row must never clobber the active row for the same symbol, which is
        exactly what BSE's three status buckets would otherwise do when a ticker
        gets reused.
        """
        merged: dict[InstrumentKey, InstrumentDTO] = {}
        symbol_sources: dict[InstrumentKey, list[str]] = defaultdict(list)

        for result in results:
            for dto in result.instruments:
                key = (dto.exchange, dto.trading_symbol)
                symbol_sources[key].append(result.source)
                existing = merged.get(key)
                if existing is None:
                    merged[key] = dto
                    continue
                merged[key] = self._prefer(existing, dto)

        for key, sources in symbol_sources.items():
            if len(sources) > 1 and len(set(sources)) > 1:
                report.duplicates.append(DuplicateGroup(
                    kind="symbol", identity=key[1], exchange=key[0],
                    members=[key[1]], sources=sorted(set(sources)),
                ))

        self._flag_isin_duplicates(merged, report)
        return merged

    @staticmethod
    def _prefer(a: InstrumentDTO, b: InstrumentDTO) -> InstrumentDTO:
        """Pick the more authoritative of two rows for the same symbol."""
        # An active listing always wins over a retired one.
        if a.is_active != b.is_active:
            return a if a.is_active else b
        if a.is_delisted != b.is_delisted:
            return a if not a.is_delisted else b

        # Otherwise prefer the richer row.
        def richness(dto: InstrumentDTO) -> tuple[bool, bool, bool]:
            return bool(dto.isin), bool(dto.listing_date), bool(dto.industry)

        return a if richness(a) >= richness(b) else b

    @staticmethod
    def _flag_isin_duplicates(
        merged: dict[InstrumentKey, InstrumentDTO], report: UniverseReport
    ) -> None:
        """One ISIN mapping to several *live* symbols on the same exchange is a data
        error; across exchanges it is normal dual listing and handled by cross-mapping.

        Retired rows are excluded: an ISIN legitimately accumulates dead counters
        over a company's life, and flagging those would bury the real collisions.
        """
        by_isin: dict[tuple[Exchange, str], list[str]] = defaultdict(list)
        for (exchange, symbol), dto in merged.items():
            if dto.isin and dto.is_active and not dto.is_delisted:
                by_isin[(exchange, dto.isin)].append(symbol)
        for (exchange, isin), symbols in by_isin.items():
            if len(symbols) > 1:
                report.duplicates.append(DuplicateGroup(
                    kind="isin", identity=isin, exchange=exchange,
                    members=sorted(symbols),
                    sources=sorted({
                        merged[(exchange, s)].source or "?" for s in symbols
                    }),
                ))

    @staticmethod
    def _cross_map_isins(
        merged: dict[InstrumentKey, InstrumentDTO], report: UniverseReport
    ) -> None:
        """Link the NSE and BSE listings of the same company via shared ISIN.

        Both rows end up carrying both tickers, so a strategy holding the NSE line
        can resolve its BSE counterpart (and vice versa) without a lookup table.

        Only *live* listings participate. An ISIN outlives the counters created
        against it — buyback tenders, pre-merger lines, renamed scrips — and those
        retired rows share the ISIN of the company that is still trading. Mapping
        them would both corrupt the dead row's identity and make the choice of
        "the" BSE ticker depend on dictionary order.
        """
        by_isin: dict[str, list[InstrumentDTO]] = defaultdict(list)
        for dto in merged.values():
            if dto.isin and dto.is_active and not dto.is_delisted:
                by_isin[dto.isin].append(dto)

        cross_mapped = 0
        for isin, listings in by_isin.items():
            per_exchange: dict[Exchange, list[InstrumentDTO]] = defaultdict(list)
            for dto in listings:
                per_exchange[dto.exchange].append(dto)
            if Exchange.NSE not in per_exchange or Exchange.BSE not in per_exchange:
                continue
            # Two live listings for one ISIN on one exchange is unresolvable without
            # guessing. Report it rather than pick one and silently mislink.
            ambiguous = {
                exchange: [d.trading_symbol for d in rows]
                for exchange, rows in per_exchange.items() if len(rows) > 1
            }
            if ambiguous:
                for exchange, symbols in ambiguous.items():
                    report.duplicates.append(DuplicateGroup(
                        kind="isin_ambiguous_mapping", identity=isin,
                        exchange=exchange, members=sorted(symbols),
                        sources=sorted({d.source or "?" for d in per_exchange[exchange]}),
                    ))
                continue
            nse = per_exchange[Exchange.NSE][0]
            bse = per_exchange[Exchange.BSE][0]
            for dto in listings:
                dto.nse_symbol = nse.trading_symbol
                dto.bse_symbol = bse.trading_symbol
            cross_mapped += 1
        report.cross_mapped = cross_mapped

    # --- phase 2: reconciliation -----------------------------------------
    def reconcile(self, report: UniverseReport) -> ReconciliationReport:
        """Write the discovered universe into the Instrument Master."""
        if self._db is None:
            raise RuntimeError("reconcile() requires a database session")
        started = time.perf_counter()
        out = ReconciliationReport()

        discovered = {(d.exchange, d.trading_symbol): d for d in report.instruments}
        exchanges = {d.exchange for d in report.instruments}
        existing = {
            (row.exchange, row.trading_symbol): row
            for row in self._db.execute(
                select(Instrument).where(Instrument.exchange.in_(exchanges))
            ).scalars()
        }

        for key, dto in discovered.items():
            row = existing.get(key)
            if row is None:
                self._db.add(self._to_model(dto))
                out.created += 1
                continue
            if self._apply(row, dto):
                out.updated += 1
                if dto.is_active and not row.is_active:
                    out.reactivated += 1
                if dto.is_delisted:
                    out.delisted += 1
            else:
                out.unchanged += 1

        # Retire what the exchange no longer lists — but only where discovery was
        # complete. A failed source means "unknown", not "gone".
        safe = report.healthy_exchanges
        out.skipped_exchanges = sorted(e.value for e in exchanges - safe)
        for key, row in existing.items():
            if key in discovered or key[0] not in safe:
                continue
            if row.is_active:
                row.is_active = False
                out.deactivated += 1

        self._db.commit()
        out.duration_seconds = time.perf_counter() - started
        self._metrics.incr("instruments_created", value=out.created)
        self._metrics.incr("instruments_updated", value=out.updated)
        self._metrics.incr("instruments_deactivated", value=out.deactivated)
        log.info("universe_reconciled", **out.summary())
        return out

    @staticmethod
    def _to_model(dto: InstrumentDTO) -> Instrument:
        return Instrument(
            trading_symbol=dto.trading_symbol, name=dto.name, exchange=dto.exchange,
            asset_class=dto.asset_class, instrument_type=dto.instrument_type,
            isin=dto.isin, nse_symbol=dto.nse_symbol, bse_symbol=dto.bse_symbol,
            exchange_token=dto.exchange_token,
            sector=dto.sector, industry=dto.industry, lot_size=dto.lot_size,
            tick_size=dto.tick_size, currency=dto.currency,
            listing_date=dto.listing_date,
            is_active=dto.is_active, is_delisted=dto.is_delisted,
        )

    @staticmethod
    def _apply(row: Instrument, dto: InstrumentDTO) -> bool:
        """Copy changed fields onto an existing row. Returns True if anything moved."""
        changed = False
        for attr in _SYNCED_FIELDS:
            new = getattr(dto, attr)
            # Discovery sources vary in richness; never overwrite a known value
            # with a blank one just because this run's source didn't carry it.
            if new in (None, ""):
                continue
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                changed = True
        return changed

    # --- convenience ------------------------------------------------------
    def sync(
        self,
        exchanges: set[Exchange] | None = None,
        asset_classes: set[AssetClass] | None = None,
    ) -> tuple[UniverseReport, ReconciliationReport]:
        report = self.discover(exchanges=exchanges, asset_classes=asset_classes)
        return report, self.reconcile(report)
