# ADR 0017 — Background-task failure recovery

**Status:** Accepted (2026-08-02). Additional decision 6 of the design-package approval.

## Context

The platform runs many long-running background tasks (Celery): universe/calendar sync, continuous market-data
validation, reconciliation sweeps, backtest/optimization runs, the outbox relay, and MTM/EOD jobs. A crash or
restart mid-task must never leave inconsistent trading state (double-fills, lost postings, orphaned
reservations, half-applied migrations of state).

## Decision

Every long-running background task must support:

- **Checkpointing** — durable, resumable progress markers (PK-range cursors, per-window checkpoints). The
  market-data validation harness's resumable checkpoint ledger is the reference pattern.
- **Safe restart** — resume from the last checkpoint, never from scratch, never corrupting partial work.
- **Idempotent execution** — re-running a task/step yields the same result, keyed on stable ids (`event_id`,
  `(order_id, fill_seq)`, ledger `dedup_key`, checkpoint cursor). Builds on ADR 0008 idempotency.
- **Duplicate protection** — task-level locks/leases (Redis) prevent concurrent duplicate runs; unique
  constraints prevent duplicate writes.
- **Atomic state transitions** — DB effects commit transactionally (with the outbox row): fully applied or not
  applied, never half.

Because OMS state is event-sourced with a transactional outbox, a crashed task's un-relayed events drain on
restart and idempotent consumers ignore replays. Reconciliation jobs detect residual inconsistency and page.

Full design in `docs/design/monitoring-observability.md` §10.

## Consequences

- (+) Crash-safety: no inconsistent trading state after any restart.
- (+) Uniform recovery pattern across all background work; operationally predictable.
- (−) Every task must be authored for resumability/idempotency (no fire-and-forget); enforced by a task
  checklist and failure-injection drills.

## References
`docs/design/monitoring-observability.md` §10, ADR 0008 (event sourcing/outbox), `trade-bot-continuous-validation-service` memory.
