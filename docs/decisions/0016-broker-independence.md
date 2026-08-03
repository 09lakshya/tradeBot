# ADR 0016 — Broker independence via a unified execution contract

**Status:** Accepted (2026-08-02). Additional decision 5 of the design-package approval. Extends ADR 0012.

## Context

Paper trading now and live broker connectivity later must not fork the core. If the OMS, Portfolio, Risk, or
Backtesting engines learn broker-specific details, then paper→live becomes a rewrite and the backtester drifts
from reality. ADR 0012 established that the backtester reuses the OMS execution path; this ADR generalizes the
principle to broker independence.

## Decision

The **OMS, Portfolio Manager, Risk Engine, and Backtesting Engine must never depend on broker-specific
implementations.** All execution flows through the **broker/execution abstraction** — the `ExecutionVenue`
contract (`submit / cancel / replace` + a fill callback stream). Implementations:

- **PaperVenue** — the simulator (now).
- **BacktestVenue** — the same fill/cost engines driven by a replay Clock (ADR 0012).
- **LiveBrokerVenue** — a future adapter; broker-specific concerns (auth, order-type mapping, rate limits,
  reconciliation quirks) live entirely inside it.

Paper and live execution share the **same execution contract**, so nothing above the venue boundary knows which
one served a fill. Both implementations must pass the **same contract test suite**.

## Consequences

- (+) paper→live is a driver swap, not a rewrite; the core is provably broker-agnostic.
- (+) One execution/cost/risk path across paper, backtest, and live — no simulator/live drift (with ADR 0012).
- (+) New brokers/venues added without touching core domains.
- (−) The contract must be broker-agnostic yet expressive enough for real brokers; risk of leaky abstractions,
  mitigated by the shared contract tests and keeping broker quirks inside adapters.

## References
`docs/design/oms-paper-trading-core.md` §1.4, ADR 0012 (shared execution venue),
`docs/design/backtesting-architecture.md`, `docs/design/risk-engine.md`.
