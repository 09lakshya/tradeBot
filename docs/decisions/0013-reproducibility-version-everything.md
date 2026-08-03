# ADR 0013 — Deterministic replay & version-everything

**Status:** Accepted (2026-08-02). Additional decisions 1 & 2 of the design-package approval.

## Context

Auditability and trust require answering "why did this exact trade happen, and can I reproduce it?" for any
historical decision, forever. That is impossible if inputs mutate under a trade or if replay is best-effort.

## Decision

1. **Deterministic replay is a first-class capability.** Any paper-trading session is reproducible from a
   pinned manifest — `{data_snapshot, event_log_range, strategy_version, model_version, config_snapshot, seed}`
   — and replay (ReplayClock, ADR 0009) reproduces **identical** OMS behavior (orders, fills, postings,
   positions, portfolio, risk verdicts). A session that does not replay byte-identically is a correctness bug,
   surfaced like a failed reconciliation.
2. **Version everything.** Every trade carries an immutable `OrderProvenance` stamp referencing immutable
   versions of: strategy, model, cost profile, risk profile, market-data provider, and feature set (+ config
   snapshot, ADR 0014). Version rows are append-only; artifacts are content-addressed. Nothing a trade points
   to can ever change under it.

Full design in `docs/design/reproducibility-and-configuration.md`.

## Consequences

- (+) Complete, permanent causal reconstruction of any decision; true bug reproduction and AI-decision replay.
- (+) Replay-verification becomes a CI/monitoring gate on correctness.
- (−) More version tables and a provenance stamp on every order; storage + discipline cost, justified by the
  auditability mandate. Mitigated by content-addressed dedup.

## References
`docs/design/reproducibility-and-configuration.md`, ADR 0008 (event sourcing), ADR 0009 (Clock/Decimal),
ADR 0014 (config-as-data).
