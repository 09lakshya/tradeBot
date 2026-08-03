# ADR 0004 — Instrument discovery is separate from price providers

**Status:** Accepted (2026-07-23)

Supersedes the parts of [ADR 0003](0003-provider-abstraction.md) that assumed the
instrument universe would arrive through `MarketDataProvider.fetch_instruments`.

## Context

The platform must trade the whole market, not a curated watchlist. That requires
an authoritative answer to "what instruments exist?" — including retired ones,
because distinguishing *delisted* from *the feed broke* is what keeps a bad sync
from wiping the Instrument Master.

`MarketDataProvider` already had a `fetch_instruments` method, but the provider
we actually use cannot implement it: Yahoo exposes no instrument-universe
endpoint and (correctly) raised rather than fabricating one. Every other
candidate price vendor has the same gap for Indian equities. The result was an
interface method that no real provider could satisfy, and a platform whose
universe would have come from a hardcoded list.

The two questions turn out to have different best answers:

| | Best source |
|---|---|
| "What did RELIANCE trade at?" | a price vendor |
| "What instruments exist on BSE?" | BSE |

Coupling them forces the platform onto whichever vendor happens to do both,
which for Indian markets is none of them.

## Decision

Introduce `InstrumentSource` as a **separate abstraction** from
`MarketDataProvider`. A source is the authority for one (exchange, asset class)
slice and returns `InstrumentDTO` rows including lifecycle state.

Implemented against the exchanges' own published lists:

| Source | Feed | Live count |
|---|---|---|
| `nse_equity` | `EQUITY_L.csv` | 2,386 |
| `nse_etf` | `eq_etfseclist.csv` | 332 |
| `nse_index` | `api/allIndices` | 139 |
| `bse_equity` | `ListofScripData` × {Active, Delisted, Suspended} | 10,773 |

`InstrumentUniverseService` runs in two phases:

1. **Discover** — merge, deduplicate, normalize ISINs, cross-map dual listings.
   Pure computation, no database, inspectable before anything is written.
2. **Reconcile** — create, update, and retire rows in the Instrument Master.

The same pattern covers the trading calendar (`HolidaySource`), which was
previously a hardcoded list and was measurably wrong — see below.

## Consequences

- (+) The universe is the market, discovered fresh, not a maintained list.
- (+) Adding futures, mutual funds, or US equities is a new source plus a
  registry entry. No other layer changes.
- (+) Delisting detection is authoritative, because BSE's retired scrips are
  fetched deliberately rather than inferred from absence.
- (−) Two abstractions to understand instead of one.
- (−) Exchange endpoints are undocumented and need browser headers and a cookie
  handshake; they can change without notice. Each source is thin and isolated so
  a break is contained, and `SourceResult` records the failure rather than
  raising.

## Notable design rules

- **A failed source never retires instruments.** Reconciliation only deactivates
  rows for exchanges whose every source succeeded (`UniverseReport
  .healthy_exchanges`). An outage must not read as the market delisting itself —
  this is the single most destructive failure mode in the layer.
- **Sentinel ISINs are rejected, not stored.** BSE publishes the literal `"NA"`
  for ~1,660 scrips; stored verbatim every one of them collides with every other
  and cross-mapping links unrelated companies. An untrustworthy ISIN is worth
  strictly less than no ISIN, so `InstrumentDTO` normalizes anything failing
  ISO 6166 to `None`.
- **Only live listings are cross-mapped.** An ISIN outlives the counters created
  against it — buyback tenders, pre-merger lines, renamed scrips. Mapping those
  corrupted the dead row's identity and made the choice of "the" BSE ticker
  depend on dictionary order. Where two live listings share one ISIN on one
  exchange, the ambiguity is reported rather than resolved by guessing.
- **A sparse source never blanks a richer one.** Reconciliation skips empty
  incoming values instead of overwriting known metadata with `None`.
- **The calendar is discovered, not hardcoded.** The shipped 2026 holiday list
  had two phantom holidays (which quarantined real bars) and was missing eleven
  actual ones. Holidays are now pulled from NSE's holiday master, and the
  calendar reports which years it can actually speak to — outside those years it
  answers "unknown" rather than "normal trading day", so quarantine can never
  discard history the calendar has no authority over.
