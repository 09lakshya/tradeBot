# ADR 0009 — Deterministic execution: Clock abstraction + fixed-point Decimal

**Status:** Accepted (2026-08-02). Cross-cutting mandates of the OMS approval.

## Context

Two classes of non-determinism silently corrupt a trading system:
1. **Time coupling** — calling the system clock directly makes tests flaky, replay impossible, and simulation
   inaccurate; trading logic is inherently time-dependent (sessions, TIF, MTM cadence, expiry).
2. **Floating-point money** — binary floats cannot represent decimal money exactly; accumulated rounding
   produces wrong balances, fees, and P&L. Unacceptable given the double-entry integrity invariants (ADR 0007).

## Decision

1. **Clock abstraction.** No code calls `datetime.now()`/`time.time()` for *business/trading* time. A `Clock`
   interface supplies time; implementations: `SystemClock` (live), `ReplayClock` (event-driven, advances to
   each event's `occurred_at`), `SimClock` (backtest/simulation). Injected everywhere trading time is needed.
   *Exception:* auth token TTLs and infra timeouts may use wall time (documented in the security design) — the
   mandate governs trading/business time, enabling replay and deterministic tests.
2. **Fixed-point Decimal everywhere** for prices, quantities, money, fees, taxes: `Decimal` in code, `NUMERIC`
   in the DB. No float in any monetary or quantity path. Rounding is explicit and specified per charge (Indian
   cost model rounding rules) — never implicit binary rounding.
3. **Determinism contract.** Given identical `(inputs, config, seed, Clock stream)`, every engine (fill, cost,
   risk, portfolio) produces identical outputs. Randomness (e.g. stochastic slippage) is seeded per
   `(order_id, fill_seq)`.

## Consequences

- (+) Exact money arithmetic; balances and P&L are reproducible and reconcilable.
- (+) Deterministic tests, replay (ADR 0008), and backtest≡paper parity (ADR 0012) become possible.
- (+) Historical replay and simulation share the exact code path as live — no simulator drift.
- (−) Developers must thread the Clock through call sites and resist `datetime.now()`/float convenience;
  enforced by review, lint rules, and tests that inject a fake clock and assert determinism.

## References
`docs/design/oms-paper-trading-core.md` §5.6/§17, `docs/design/ledger-architecture.md`,
`docs/design/backtesting-architecture.md`.
