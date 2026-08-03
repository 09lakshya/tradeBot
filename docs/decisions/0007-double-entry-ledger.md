# ADR 0007 — Cash ledger is full append-only double-entry

**Status:** Accepted (2026-08-02). Decision 1 of the OMS approval.

## Context

The OMS design offered a choice (open question 1): a single-entry `transactions` ledger with `balance_after`,
or a stricter model. Money correctness is existential for this platform — a wrong balance that "looks" right is
the worst failure mode. Single-entry ledgers make it easy to record an unbalanced or unexplained movement.

## Decision

Implement a **full append-only double-entry ledger**:
- Every economic event (order, fee, tax, dividend, corporate action, adjustment, funding) posts a **balanced
  journal** — total debits equal total credits — against a typed account chart.
- **Never update balances directly.** A balance is always derived as `SUM(entries)`; a cached projection exists
  **only for performance** and is fully rebuildable from entries.
- **No updates, no deletes, no in-place edits.** Immutability enforced in depth: service layer, DB
  `REVOKE UPDATE/DELETE` + trigger, append-only partitioning.
- Every entry is timestamped (Clock-sourced UTC), carries correlation/causation metadata, and one entry **per
  charge class** (never netted) for independent auditability.
- Charges settle into a versioned account chart (`assets/liabilities/equity/income/expenses`); the standing
  invariant `Assets = Liabilities + Equity` holds at all times.

Full design in `docs/design/ledger-architecture.md`.

## Consequences

- (+) Self-checking integrity: `SUM(signed_amount)=0` per posting and a whole-book trial balance make silent
  corruption detectable and alertable.
- (+) Complete auditability and reconstructable balances (event-sourcing friendly).
- (+) Reconciliation jobs (posting balance, trial balance, cost-basis vs positions, projection vs entries)
  become first-class monitoring signals.
- (−) More writes per event and a richer schema than single-entry; mitigated by cached projections for reads.
- (−) Existing single-entry `transactions` must be superseded by `ledger_entries`; trivial now (greenfield, no
  production data) via the expand/contract migration plan.

## References
`docs/design/ledger-architecture.md`, `docs/design/database-migration-plan.md`.
