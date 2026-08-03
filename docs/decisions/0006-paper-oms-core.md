# ADR 0006 — Paper Trading Core / OMS architecture

**Status:** Accepted (2026-08-02). Approved by the user with five locked decisions + cross-cutting mandates.

## Context

After the Market Data Layer was validated, the next correctness-critical layer is the Order Management System /
Paper Trading Core (ADR 0011 sequencing). A full design was delivered in
`docs/design/oms-paper-trading-core.md` with five open questions. The user reviewed and approved it, resolving
all five and adding cross-cutting mandates.

## Decision

Adopt the OMS design as specified, with these locked decisions:

1. **Cash ledger — full append-only double-entry** (see ADR 0007).
2. **Terminal order immutability** enforced primarily at the domain/service layer, with DB constraints as
   additional protection. Terminal states (`filled|cancelled|rejected|expired`) allow only append-only audit
   events afterward.
3. **Expanded order lifecycle:** `created → validated → accepted → pending → partially_filled →
   filled|cancelled|rejected|expired`; maintain backward compatibility where practical (`partial →
   partially_filled`).
4. **Configurable MTM cadence** — defaults: position MTM per price update, portfolio MTM every 5s, dashboard via
   WebSocket, EOD snapshot at market close.
5. **Buying-power reservation on `accepted`**, released on cancel/expire/reject, adjusted incrementally on
   partial fills.

Cross-cutting mandates bind all OMS code: idempotency keys on submission; full event metadata (ADR 0008);
event-sourced replay; Clock abstraction and fixed-point Decimal (ADR 0009); deterministic concurrency safety;
day-replayability.

The Fill/Cost engine sits behind an `ExecutionVenue` interface (paper venue now; backtest and future live
broker reuse it — ADR 0012). The Risk Engine is a mandatory pre-trade gate (ADR 0010).

## Consequences

- (+) Professional-grade, auditable OMS with a single execution path shared across paper/backtest/live.
- (+) All five design ambiguities resolved before any code — no architectural rework expected mid-build.
- (−) More upfront machinery (outbox, event store, double-entry) than a naive OMS; justified by correctness-
  first goals and the auditability/replay requirements.

## Implementation gate

Code begins **only after** the PostgreSQL/TimescaleDB validation passes. Then: implement OMS incrementally →
**pause for review before the Risk Engine**.

## References
`docs/design/oms-paper-trading-core.md` (§17 records the approval), and the supporting designs: ledger,
event-schemas, oms-event-flows, database-migration-plan.
