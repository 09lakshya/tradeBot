# Monitoring & Observability — Technical Design

**Status:** Approved design (design-only) · **Phase:** Design-only · **Depends on:** existing
`app/core/logging.py`, `/health` + `/health/ready` endpoints (already built during PG-validation prep),
event architecture, ledger reconciliation.

> A trading system's worst failures are **silent**: a wrong balance, a missed fill, a stale feed that still
> "looks" live. Observability here is designed to make correctness failures *loud*, not just track uptime.

---

## 1. The four pillars

1. **Metrics** — numeric time series (Prometheus-style), for rates/latencies/gauges and business KPIs.
2. **Logs** — structured, correlated event records for forensic detail.
3. **Traces** — request/flow spans tied by `correlation_id` across domains.
4. **Reconciliation checks** — domain-specific invariants (the trading-correctness pillar most systems omit).

---

## 2. Metrics

- **Transport:** app exposes `/metrics` (Prometheus text format); scraped by Prometheus; visualized in Grafana.
  Registry lives in a `core/metrics.py` (design: thin wrapper so domains register counters/histograms).
- **Naming:** `tradebot_<domain>_<name>_<unit>` with labels (domain, instrument-class, portfolio, outcome).

**System metrics:** request latency histograms (per route), error rates, DB pool usage & query latency, Redis
latency/hit-rate, Celery queue depth & task latency, event-loop lag, process CPU/mem.

**Pipeline metrics:** market-data ingestion lag & freshness per instrument, provider failover count, cache
hit-rate, calendar/universe sync status, bars-quarantined count.

**Business/correctness metrics (the important ones):**
| Metric | Why it matters |
|---|---|
| `oms_orders_total{state}` / rejection reasons | order-flow health & risk-block rates |
| `oms_fill_latency_seconds` | execution responsiveness |
| `oms_slippage_bps` (modeled vs realized) | execution-model drift → circuit breaker |
| `ledger_reconciliation_status` | trial-balance / projection integrity (0=ok) |
| `ledger_posting_imbalance_total` | should be **0 forever**; any non-zero pages immediately |
| `risk_blocks_total{rule}` / `risk_kill_switch_state` | risk posture at a glance |
| `portfolio_equity` / `portfolio_drawdown` | live P&L & risk |
| `outbox_unpublished_events` / age | event-delivery backlog (recovery health) |
| `data_feed_staleness_seconds{instrument}` | stale-feed detection (silent-failure guard) |

## 3. Logging

- **Structured JSON** via the existing `logging.py` (extend to always inject `correlation_id`, `causation_id`,
  `aggregate_id` from a context var). One event = one log line, machine-parseable.
- **Levels & discipline:** `INFO` for lifecycle transitions, `WARNING` for degraded-but-handled (provider
  failover, cache miss storm), `ERROR` for failures needing attention, `CRITICAL` for correctness violations
  (posting imbalance, reconciliation mismatch, gate bypass attempt).
- **Correlation:** every log within a flow shares `correlation_id`, so an order's entire life (submit → risk →
  fills → postings → portfolio) is one query. Ties directly to the event log.
- **Sensitive-data policy:** never log secrets, full tokens, or PII; redact at the formatter (see security
  design). Financial amounts are fine in an internal system but are access-controlled.
- **Retention/shipping:** ship to a log store (Loki/ELK or cloud equivalent); hot retention for ops, cold
  archive for audit. Immutable audit-relevant logs mirror the append-only event store rather than replace it.

## 4. Tracing

- **OpenTelemetry** spans across FastAPI → service → DB/Redis/Celery, propagating `correlation_id`. An order
  flow is a trace; each domain hop a span. Enables latency attribution on the hot order path (risk gate budget,
  fill, ledger post) and root-causing cross-domain slowdowns.

## 5. Alerting

- **Tiers:** `page` (wake someone — correctness/safety), `ticket` (next business day), `info` (dashboard only).
- **Alertmanager** routes by severity/scope; dedup + grouping to avoid storms.

| Alert | Tier | Condition |
|---|---|---|
| Ledger imbalance / reconciliation fail | **page** | any `ledger_posting_imbalance_total>0` or trial balance ≠ 0 |
| Risk gate error / fail-closed spike | **page** | risk evaluation errors or block-rate anomaly |
| Kill switch tripped | **page** | `risk_kill_switch_state=tripped` |
| Data feed stale | **page** during session | `data_feed_staleness > threshold` for tradable instruments |
| Outbox backlog growing | ticket→page | unpublished events age beyond SLA (event-delivery health) |
| Slippage model drift | ticket | realized vs modeled slippage diverges beyond band |
| DB/Redis degraded | page | `/health/ready` failing, pool exhaustion, replica lag |
| Celery queue backlog | ticket | queue depth/latency beyond SLA |

- **Fatigue control:** every alert has a runbook link, a clear owner, and a tested threshold; no alert without
  an action. Correctness alerts are never auto-silenced.

## 6. Dashboards

- **Ops:** service health, latency/error SLOs, DB/Redis/Celery, feed freshness, outbox backlog.
- **Trading:** live equity/P&L, positions & exposures, order flow & rejection reasons, risk limits utilization,
  kill-switch/breaker states.
- **Data quality:** universe/calendar sync, bars quarantined, provider failover, adjustment-continuity checks
  (ties to ADR 0005 validation).
- **Research:** study progress, IS/OOS gap (overfit monitor), promotion/rollback timeline.
- Real-time trading views are driven by the same WebSocket `portfolio.updated`/`metrics.updated` stream the app
  serves to users (single source, no separate path).

## 7. Health endpoints (existing, extended)

- **`/health`** — liveness only (process up). Already built.
- **`/health/ready`** — readiness: PG + Redis reachable with a 2s connect timeout (built during PG-validation
  prep; the timeout fixed a ~21s Windows hang). Extend to include: alembic head applied, outbox relay alive,
  Clock source healthy, and last-reconciliation status. Used by the load balancer / orchestrator to gate
  traffic and by deploys to verify a release.
- **`/health/startup`** (future) — startup probe for slow first-boot (migrations, warm caches).

## 8. Failure recovery (operational)

- **Event-sourced recovery:** state rebuildable from the append-only log; outbox drains on restart (no event
  loss) — see `oms-event-flows.md` §7. Monitoring surfaces outbox age and rebuild events.
- **Runbooks** (docs, per alert): ledger-imbalance investigation, projection rebuild, feed-stale failover,
  kill-switch reset procedure, DB failover/restore, migration rollback.
- **Backups & DR:** managed-PG automated backups + PITR; `deploy/backup.sh` exists for logical dumps;
  restore drills are a scheduled exercise. RPO/RTO targets documented per environment.
- **Chaos/failure drills:** periodically kill the relay, sever Redis, stale a feed, and assert the system
  degrades safely (queues, fail-closed risk, alerts fire) — the resilience already validated for the market-
  data layer, extended to OMS.

## 9. Performance targets (locked 2026-08-02 — engineering targets, not guarantees)

These are **measurable objectives** tracked as SLOs, monitored via the latency histograms in §2. They are
targets the system is designed and tested against, not contractual guarantees.

| Target | Objective (p99 unless noted) | Notes |
|---|---|---|
| Order validation | **< 50 ms** | structural + risk-gate pipeline; risk gate itself budgeted < 20 ms as a sub-step |
| Paper order execution | **< 200 ms** | submit → filled (happy path), incl. fill + ledger post + reservation release |
| Portfolio update | **< 100 ms** | fill/mark → `portfolio.updated` projection |
| Dashboard API | **< 300 ms** | read endpoints backing the UI |
| Background reconciliation | **configurable** | cadence set via config (§ config-as-data); not on the hot path |
| Ledger imbalance incidents | **0** (hard) | any non-zero pages immediately |
| Event delivery lag | < 2 s | outbox → consumers |
| Feed freshness (session) | < 5 s | stale-feed guard |
| Readiness true during market hours | ≥ 99.9% | `/health/ready` |

Each target has a corresponding metric + alert; regressions are caught in CI performance checks and in
production dashboards. Targets are themselves stored as configurable thresholds (config-as-data), so they can
be tuned per environment without code changes.

## 10. Background-task failure recovery (locked 2026-08-02)

Every long-running background task (Celery jobs: universe/calendar sync, continuous market-data validation,
reconciliation sweeps, backtest/optimization runs, outbox relay, MTM/EOD jobs) must be **crash-safe**. A system
crash must **never** leave inconsistent trading state.

**Required properties for every background task:**
- **Checkpointing** — durable, resumable progress markers (e.g. PK-range cursors, per-window checkpoints). The
  market-data validation harness already models this (resumable SQLite checkpoint ledger); the pattern is the
  standard for all long tasks.
- **Safe restart** — a task killed mid-run resumes from its last checkpoint, not from the beginning, and never
  corrupts partial work.
- **Idempotent execution** — re-running a task (or a step) produces the same result; keyed on stable ids
  (`event_id`, `(order_id, fill_seq)`, ledger `dedup_key`, checkpoint cursor). Ties to the event-sourcing
  idempotency guarantees (ADR 0008).
- **Duplicate protection** — task-level locks/leases (Redis) prevent two workers running the same job
  concurrently; unique constraints prevent duplicate writes if they do.
- **Atomic state transitions** — a task's DB effects commit transactionally (with the outbox row) so a crash
  leaves either "fully applied" or "not applied", never half-applied.

**Consequence for trading state:** because OMS state is event-sourced with a transactional outbox, a crashed
task's un-relayed events drain on restart and idempotent consumers ignore replays — so no double-fills, no
lost postings, no orphaned reservations. Reconciliation jobs (§2) detect any residual inconsistency and page.

## 11. SLO governance
SLO thresholds live in the versioned config store (config-as-data); changes are audited. Breach budgets and
error budgets are reviewed as the system matures.
