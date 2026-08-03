# ADR 0012 — Backtester reuses the OMS execution/cost/risk engines (`ExecutionVenue`)

**Status:** Accepted (2026-08-02). Design in `docs/design/backtesting-architecture.md`.

## Context

The single most dangerous failure for a strategy platform is a backtester that disagrees with reality — a
"lying backtester" that reports profits the paper/live system never earns. This happens when the backtest is a
*separate* simulator with its own fill logic, cost model, and risk handling that drift from production.

## Decision

There is **one** execution path, exposed behind an `ExecutionVenue` interface. The paper OMS, the backtester,
and (future) live broker connectivity are all **implementations/drivers** of the same Fill Engine, Cost Engine
(Indian charges), double-entry Ledger, and Risk Engine:

- The **backtester** drives these shared engines with a **replay Clock** over historical bars (ADR 0009).
- The **cost model** is the same versioned `cost_profiles`; backtest P&L posts through the **same double-entry
  ledger** (isolated per-run portfolio) — not a parallel approximation.
- The **Risk Engine** rules are the same code in backtest and paper, so there is no risk drift.
- Conservative, deterministic fill/slippage defaults (next-bar-open fills, seeded slippage) prevent look-ahead
  and over-optimism.

## Consequences

- (+) backtest ≡ paper ≡ live behavior by construction — the strongest defense against simulator drift.
- (+) Net-of-cost, risk-consistent results; realistic capacity/slippage.
- (+) Reproducible runs (pinned data snapshot + code version + seed) enable CI regression on strategy results.
- (−) The shared engines must be written test-first and kept driver-agnostic (no paper-only or backtest-only
  shortcuts); enforced by the `ExecutionVenue` boundary and parity tests.

## References
`docs/design/backtesting-architecture.md`, `docs/design/oms-paper-trading-core.md` (§1.4, §5),
`docs/design/risk-engine.md`, `docs/decisions/0005-provider-aware-adjustment.md` (no re-adjustment in backtest).
