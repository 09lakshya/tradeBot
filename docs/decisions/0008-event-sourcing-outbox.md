# ADR 0008 — Event sourcing with a transactional outbox

**Status:** Accepted (2026-08-02). Implements the Event Metadata + Event Replay mandates of the OMS approval.

## Context

The OMS must be fully auditable and reconstructable ("no business state may become unrecoverable"), support
bug reproduction and AI-decision replay, and deliver events to consumers (metrics, WS, analytics) without loss
or duplication — even across crashes. A naive "write state, then publish an event" approach can lose or
duplicate events if the process dies between the two steps (dual-write problem).

## Decision

1. **Event sourcing for OMS state.** The append-only event log (`order_events` + `ledger_entries` + a general
   `event_store`) is the system of record. Projections (order book, positions, cash balances, portfolio) are
   derived read models, rebuildable by folding events through pure reducers. Complete OMS state is
   reconstructable from the log alone.
2. **Mandatory event envelope** on every event: `event_id, event_type, event_version, aggregate_type,
   aggregate_id, sequence, occurred_at, recorded_at, correlation_id, causation_id, producer, payload`.
   `sequence` is per-aggregate monotonic and doubles as the optimistic-concurrency version.
3. **Transactional outbox.** Each state change writes its events and an `oms_outbox` row in **one DB
   transaction**. A relay publishes unpublished rows to the in-process bus + Redis (for WS), marking them
   published. If Redis is down, events queue and drain on recovery — no loss.
4. **Idempotent consumers** keyed on `event_id` (and `(order_id, fill_seq)` / ledger `dedup_key`), so
   at-least-once delivery is safe.
5. **Schema versioning** with upcasters (`vN → vN+1`) applied at read/replay time; stored events are never
   mutated.

Full designs in `docs/design/event-schemas.md` and `docs/design/oms-event-flows.md` (§7 recovery).

## Consequences

- (+) Exactly-once *effect* despite at-least-once delivery; crash-safe (outbox drains on restart).
- (+) Deterministic replay (with the Clock, ADR 0009) enables bug repro, day-replay validation, AI-decision
  replay, and total auditability.
- (+) `correlation_id`/`causation_id` give end-to-end traceability across domains (also powers tracing/logging).
- (−) More moving parts (outbox relay, reducers, upcasters) and discipline (every consumer must be idempotent);
  covered by contract tests and reconciliation checks.

## References
`docs/design/event-schemas.md`, `docs/design/oms-event-flows.md`, `docs/design/oms-paper-trading-core.md` §11.
