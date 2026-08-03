# Architecture

Living document. See `docs/decisions/` for ADRs and `docs/design/` for full technical specifications.

## Design specifications (approved, design-only until the PG/TimescaleDB gate passes)

| Spec | Covers | ADR |
|------|--------|-----|
| `design/oms-paper-trading-core.md` | OMS/Paper Trading Core (16 §, §17 records approval) | 0006 |
| `design/ledger-architecture.md` | Double-entry account chart, journals, projections, audit | 0007 |
| `design/event-schemas.md` | Every domain event: envelope + payload + producer/consumer | 0008 |
| `design/oms-event-flows.md` | Sequence diagrams incl. corporate actions + recovery | 0006/0008 |
| `design/database-migration-plan.md` | Expand/contract, rollback, zero-downtime, versioning | — |
| `design/risk-engine.md` | Sizing, limits, kill switch, circuit breakers, gate pipeline | 0010 |
| `design/backtesting-architecture.md` | Event engine, shared fills/costs, walk-forward, Monte Carlo | 0012 |
| `design/ai-research-architecture.md` | Discovery, HPO/Bayesian/GA/RL, registry, promotion/rollback | — |
| `design/monitoring-observability.md` | Metrics, logging, tracing, alerting, dashboards, health, perf targets, task recovery | — |
| `design/security.md` | AuthN/Z, secrets, audit, encryption, API security, rate limits | — |
| `design/reproducibility-and-configuration.md` | Deterministic replay, version-everything, config-as-data | 0013/0014 |

ADRs 0006–0017 record the OMS approval and all cross-cutting mandates: double-entry ledger (0007), event
sourcing + outbox (0008), Clock/Decimal determinism (0009), mandatory risk gate (0010), correctness-first
sequencing (0011), shared execution venue (0012), deterministic replay + version-everything (0013),
config-as-versioned-data (0014), AI isolation (0015), broker independence (0016), background-task failure
recovery (0017).

## Style

Modular monolith: one FastAPI app, domains isolated under `backend/app/domains/*`, async
work via Celery + Redis, PostgreSQL + TimescaleDB for storage. Chosen over microservices to
avoid premature distribution complexity; domain boundaries are drawn so any one can be
extracted into a service later without rewrites.

## Domains

| Domain | Responsibility |
|--------|----------------|
| `market_data` | Pluggable providers, OHLCV ingestion/caching, corporate actions |
| `trading` | Paper OMS: portfolios, orders, fills, positions, cash ledger, P&L |
| `risk` | **Mandatory pre-trade gate** — limits, risk audit trail, kill switch |
| `strategies` | Strategy interface + built-in library, signal generation |
| `backtest` | Event-driven, cost-aware, bias-protected engine; walk-forward, Monte Carlo, OOS |
| `metrics` | Equity curve + Sharpe/Sortino/CAGR/drawdown/profit-factor/expectancy |
| `research` | AI strategy search + promotion loop (**built last**) |
| `platform` | Users, JWT/RBAC auth, audit log, strategy-version registry |

## The order path (non-negotiable)

```
Strategy signal → OrderDecision (explainability) → Risk pre-trade gate
   → [pass] Paper OMS execution → Fill + Position + Transaction + EquitySnapshot
   → [block] Order.status = rejected + RiskEvent(reason)
```

No order reaches the OMS unless every risk rule passes (spec §13).

## Market Data Layer

Two independent inbound paths. **Discovery** answers *what instruments exist*;
**ingestion** answers *what did they trade at*. They deliberately use different
abstractions and different upstreams — see ADR 0004.

```
InstrumentSource × N (NSE equity/ETF/index, BSE equity)
   → merge + ISIN normalize + dedupe + dual-listing cross-map   (no DB)
   → reconcile into instruments  (create / update / retire)

ProviderRouter (rate limit → retry/backoff → failover)
   → DataQualityValidator
       ├─ pass → CorporateActionEngine (back-adjust) → upsert ohlcv → cache/metrics
       └─ fail → quarantined_data (typed reason + raw payload)
```

| Concern | Where | Note |
|---|---|---|
| Provider abstraction | `providers/base.py`, `providers/registry.py` | Config-switchable; see ADR 0003 |
| Instrument discovery | `discovery/` | Exchange-sourced universe; see ADR 0004 |
| Resilience | `providers/resilience.py` | Token bucket + exponential backoff w/ jitter |
| Instrument Master | `models.Instrument` | ISIN, NSE+BSE symbols, sector, lifecycle flags |
| Trading calendar | `calendar.py`, `discovery/calendars.py` | Synced from the exchange holiday master |
| Timeframe derivation | `resampling.py` | Session-anchored; serves frames no vendor publishes |
| Session/timezone | `sessions.py` | Per-exchange tz; all date logic is exchange-local |
| Data quality | `validation.py` | Rejects to `quarantined_data`, never to `ohlcv` |
| Corporate actions | `corporate_actions.py` | Back-adjustment keeps series continuous |
| Cache | `cache.py` | Redis w/ per-namespace TTLs, degrades to no-op |
| Observability | `observability.py` | Latency/failures/retries/hit-rate/freshness |
| Live validation | `live_validation.py` | Resumable full-market validation harness |

**Timeframes** are first-class from day one (1m…1mo); the `ohlcv` primary key is
`(instrument_id, timeframe, ts)`, so all intervals coexist per instrument. A frame
the provider does not publish (4h on Yahoo) is aggregated from a finer one rather
than left unsupported.

**Timestamps are stored in UTC and interpreted in exchange-local time.** Postgres
`TIMESTAMPTZ` normalizes to UTC anyway; writing UTC explicitly means the same code
is correct on backends that drop the offset. Every date-bounded query, calendar
check, and session check converts through `sessions.exchange_timezone` first — an
IST trading day begins at 18:30 UTC the previous date, so UTC-framed date logic
silently drops bars.

**Quarantine carries the burden of proof.** Rejection is destructive, so a bar is
only discarded on a *provable* violation. The calendar reports which years it has
authoritative coverage for and answers "unknown" elsewhere, rather than letting a
coverage gap masquerade as a closure.

**Schedulers contain no date logic.** Celery beat fires on a cron; the task asks the
Market Calendar whether the exchange traded and no-ops otherwise.

## Build order (correctness-first)

Approved implementation sequence (2026-08-02), with an **approval gate after each major subsystem**:

1. Foundation: scaffold, DB schema, migrations, auth skeleton ✅
2. Market Data Layer — providers, calendar, validation, corporate actions ✅
3. **PostgreSQL/TimescaleDB validation** — the current gate (blocked on cloud DB/Redis URLs)
4. OMS implementation — portfolio, positions, double-entry ledger, P&L (design approved, ADR 0006)
5. **OMS review** (approval gate)
6. Risk Engine — the gatekeeper (design done; review before build)
7. Backtesting Engine — correct, cost-aware, bias-protected (design done)
8. Strategy Engine — interface + built-in strategies
9. Metrics + Frontend dashboard (interleaved as subsystems land)
10. AI Research Engine — self-improvement loop (design done; built last, ADR 0015 isolation)
11. Live Broker Integration — **only after extended paper-trading validation** (ADR 0016)

> Note: Backtesting precedes the Strategy Engine **intentionally** (confirmed 2026-08-02): every strategy is
> developed and evaluated on a trusted, validated execution/cost/fill/risk engine, so no strategy is optimized
> against an unverified backtester. This is the correctness-first principle (ADR 0011) applied to ordering.
All of phases 4–11 have approved design specs under `docs/design/`; implementation remains gated on the
PostgreSQL/TimescaleDB validation and the per-subsystem review cadence.

## Data model

Time-series tables (`ohlcv`, `equity_snapshots`) are TimescaleDB hypertables; the time
column is part of their composite primary key (required for partitioning). All other tables
are standard Postgres. Enums are DB-native. Money columns use `NUMERIC` (never float) to
avoid rounding drift on P&L. `audit_log`, `transactions`, `fills`, and `risk_events` are
append-only records.

## Deployment

Local: `docker compose up`. Cloud VM: `docker-compose.prod.yml` overrides add restart
policies + workers; `deploy/provision.sh` brings up a fresh Ubuntu VM; `deploy/backup.sh`
runs nightly `pg_dump`. Provisioning the VM itself requires user-supplied credentials.
