# ADR 0011 — Correctness-first build sequencing

**Status:** Accepted (2026-07-23). Retroactively recorded as an ADR (2026-08-02).

## Context

The master spec ("Paper Trade Prompt.md") lists 13 phases. Building them in literal order would put ML/
self-improvement early, on top of an unproven core — the fastest route to a system that is confidently wrong.
For a trading platform, a subtle correctness bug (bad data, a lying backtester, a miscounted balance) is
existential and often silent.

## Decision

Build in **correctness-first** order, not the literal phase order:

```
Market Data → Paper OMS → Risk Engine → Strategy Engine → Backtester → Metrics/Dashboard   (FIRST)
AI/ML research + self-improvement loop                                                     (LAST)
```

AI/ML is built **last**, only once the core is trustworthy and every layer below it has been validated. Each
phase is **designed, then paused for explicit user approval, then implemented** (gated cadence). Each layer's
correctness is validated before the next is built (e.g. the Market Data Layer was live-validated;
PG/TimescaleDB validation gates the OMS).

## Consequences

- (+) Every layer stands on a validated foundation; AI can't amplify a broken core.
- (+) The gated cadence catches design errors before they become code.
- (−) Slower to reach the "exciting" AI features; accepted deliberately — an untrustworthy autonomous trader is
  worse than a slow one.

## References
memory `trade-bot-architecture-decisions`, `trade-bot-key-challenges`; ADRs 0006 (OMS), 0010 (Risk), 0012
(backtester), and the design docs under `docs/design/`.
