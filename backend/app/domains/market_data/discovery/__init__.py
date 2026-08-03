"""Instrument universe discovery.

Price providers answer "what did this symbol do?"; discovery sources answer
"what instruments exist at all?". They are deliberately separate abstractions:
the best OHLCV provider is rarely the best universe authority (Yahoo, for one,
exposes no instrument list), and coupling them would force the whole platform
onto whichever vendor happened to do both.

A :class:`~app.domains.market_data.discovery.base.InstrumentSource` yields
``InstrumentDTO`` rows for one (exchange, asset class) slice. The registry
composes them, and :class:`InstrumentUniverseService` merges, cross-maps, and
reconciles the result into the Instrument Master.
"""
from app.domains.market_data.discovery.base import (
    DiscoveryError,
    InstrumentSource,
    SourceResult,
)
from app.domains.market_data.discovery.registry import (
    available_sources,
    build_sources,
    register_source,
)
from app.domains.market_data.discovery.service import (
    InstrumentUniverseService,
    ReconciliationReport,
    UniverseReport,
)

__all__ = [
    "DiscoveryError",
    "InstrumentSource",
    "InstrumentUniverseService",
    "ReconciliationReport",
    "SourceResult",
    "UniverseReport",
    "available_sources",
    "build_sources",
    "register_source",
]
