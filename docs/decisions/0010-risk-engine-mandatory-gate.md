# ADR 0010 — Risk Engine is a mandatory pre-trade gate

**Status:** Accepted (2026-07-23, reaffirmed 2026-08-02). Design in `docs/design/risk-engine.md`.

## Context

An autonomous/algorithmic trading platform can generate orders faster than any human can supervise. A risk
layer that is *advisory* (logged but bypassable) is worthless the moment code paths multiply. The locked
architecture (ADR 0011) names the Risk Engine a **non-negotiable pre-trade gate**.

## Decision

The Risk Engine sits **in the order path** between `validated` and `accepted` and is the **only** transition
into `accepted`. The order state machine requires a signed `RiskVerdict.PASSED` token bound to the exact
`(order_id, order_version)`; there is no code path to `accepted` without it. Design specifics:

- **All-must-pass** ordered pipeline: structural/sanity, kill-switch/breaker state, buying-power, position
  sizing, exposure, correlation/concentration, daily-loss, drawdown, volatility, rate/churn.
- **Fail-closed:** any snapshot failure, missing config, or rule error yields `block`, never silent-pass.
- **Deterministic & pure** over a `RiskSnapshot` + Clock; every evaluation emits auditable `risk.*` events.
- **Kill switch** (manual/auto hard stop) and **circuit breakers** (auto temporary halts) integrate as
  short-circuit pipeline steps.
- **Shared with the backtester** (ADR 0012), so live and simulated risk behavior are identical.

## Consequences

- (+) No order can execute unless every safety rule passes — the platform's core safety guarantee.
- (+) Full audit trail of why every order was allowed/blocked.
- (−) Adds latency to the order path (budgeted p99 < 20ms) and a hard availability dependency; mitigated by
  building the snapshot from projections and keeping rules pure/fast.

## Implementation note

Per the OMS approval, **implementation pauses for review before the Risk Engine is built**;
`docs/design/risk-engine.md` is the review artifact.

## References
`docs/design/risk-engine.md`, `docs/decisions/0001-modular-monolith.md`, memory `trade-bot-architecture-decisions`.
