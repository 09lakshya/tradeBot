# Risk Engine — Technical Design

**Status:** Approved design (design-only) · **Phase:** Design-only — **implementation is the FIRST thing after
the OMS, and requires its own review pause** (per the approval's sequencing). **Becomes:** ADR 0010.
**Depends on:** ADR 0001, `oms-paper-trading-core.md` §10, `event-schemas.md` §3.8.

> Non-negotiable (ADR-level): the Risk Engine is a **mandatory pre-trade gate in the order path, not
> advisory**. No order reaches `accepted` unless every rule passes. This is a structural invariant, not a
> configuration.

---

## 1. Position in the order path

```
order.validated ──▶ [ RISK GATE ] ──▶ order.accepted ──▶ execution
                        │
                        └── blocked ▶ order.rejected(stage=risk, rule, detail)
```

The gate sits between `validated` and `accepted`. It is the *only* transition into `accepted`, enforced by the
order state machine: the `accept()` method requires a `RiskVerdict.PASSED` token produced by the engine for
that exact `(order_id, order_version)`. There is no code path to `accepted` that bypasses it.

Two evaluation contexts, same rule code:
- **Pre-trade (blocking):** per order submission — must return within a tight budget (target p99 < 20ms) so it
  never becomes the latency bottleneck. Rules are pure functions over a risk snapshot.
- **Continuous (monitoring):** portfolio-level rules (drawdown, daily loss, exposure) re-evaluated on
  `portfolio.updated`/`metrics.updated`; breaches can arm circuit breakers / trip the kill switch, which then
  cause *subsequent* pre-trade checks to block.

---

## 2. Validation pipeline

An order runs through an ordered pipeline of independent **rules**. Each rule is
`evaluate(order, snapshot, config) -> RuleResult(pass|block, observed, threshold, detail)`. The pipeline:

```
1. Structural / sanity        (qty>0, price>0, tick/lot size, instrument tradable, session open)
2. Kill-switch & circuit-breaker state   (short-circuit block if tripped)
3. Buying-power / cash sufficiency        (worst-case notional + charges <= available BP)
4. Position sizing limit                  (per-order and per-instrument caps)
5. Exposure limits                        (per-instrument, per-sector, gross, net)
6. Concentration / correlation limits     (correlated cluster exposure)
7. Daily loss limit                       (realized+unrealized today vs cap)
8. Drawdown limit                         (equity vs peak)
9. Volatility filter                      (instrument vol / ATR regime gate)
10. Rate / churn limits                   (orders per interval, wash-trade guard)
```

**Semantics:**
- **All-must-pass**, evaluated in order; on first `block`, short-circuit and emit `order.rejected(stage=risk)`.
  (Config option to evaluate-all for richer diagnostics in backtests.)
- Every rule evaluation emits an auditable `risk.rule_evaluated` event; the aggregate verdict emits
  `risk.checked`. This gives a complete "why blocked / why allowed" trail per order.
- Rules are **pure and deterministic** over the snapshot + Clock; identical inputs ⇒ identical verdict
  (needed for replay and backtest parity).
- **Fail-closed:** if the engine cannot produce a snapshot or a rule errors, the verdict is `block`, never
  silent-pass.

---

## 3. Rules (detailed)

### 3.1 Position sizing
- **Fixed-fractional / risk-per-trade:** max qty such that `(entry − stop) × qty ≤ risk_fraction × equity`.
- **Notional cap:** `qty × price ≤ max_position_notional` (absolute and as % of equity).
- **Kelly-capped (optional, from strategy):** strategy may *request* a size; risk only ever *reduces* it.
- Output: either pass at requested size, or block (strict mode) / propose a reduced size (advisory field,
  never auto-applied without strategy opt-in).

### 3.2 Exposure limits
- **Per-instrument:** `|net position value| ≤ max_instrument_exposure`.
- **Per-sector/industry:** roll up instrument→sector (from instrument master), cap sector gross.
- **Gross & net book:** `Σ|position value| ≤ gross_cap`; `|Σ signed value| ≤ net_cap`.
- Evaluated **post-hypothetical-fill** (would this order breach the cap if fully filled?).

### 3.3 Daily loss limit
- `today_realized_pnl + today_unrealized_delta ≤ −daily_loss_cap` ⇒ block new risk-increasing orders and arm
  a soft circuit breaker. Risk-reducing orders (closing/hedging) remain allowed (configurable).
- "Today" boundary uses the exchange session via the Clock, not wall time.

### 3.4 Drawdown limit
- Track `peak_equity` (high-water mark) and current equity from `metrics.updated`.
- `drawdown = (peak − equity)/peak`; `drawdown ≥ max_drawdown` ⇒ trip circuit breaker (halt new risk),
  optionally trip the kill switch at a harder threshold.

### 3.5 Correlation limits
- Maintain a rolling correlation matrix (from returns in the market-data layer, cached, recomputed off the hot
  path). Cluster instruments with `|ρ| ≥ ρ_threshold`.
- Cap **aggregate exposure per correlated cluster** so nominally-diversified positions that move together are
  treated as one bet. Missing/insufficient correlation data ⇒ treat as independent but flag (fail-open on the
  *limit* only, never on structural checks).

### 3.6 Volatility filters
- Per-instrument realized vol / ATR percentile vs its own history.
- Modes: **block** entries when vol above a ceiling (avoid chaos regimes), and/or **scale** max size inversely
  with vol (vol-targeting). Configurable per strategy.
- Circuit-breaker tie-in: an index-level vol spike can trip a market-wide breaker.

### 3.7 Rate / churn limits
- Max orders per instrument per interval; max cancels/replaces per interval (anti-thrash); wash-trade guard
  (block an order that would trade against the account's own resting opposite order).

---

## 4. Kill switch

A hard, human-or-system operated master stop.

- **Scopes:** global (all trading), per-portfolio, per-strategy, per-instrument.
- **States:** `armed` (normal) → `tripped` (all new risk-increasing orders blocked; existing orders may be
  auto-cancelled per policy) → `reset` (manual, audited, requires reason + actor).
- **Triggers:** manual (API/dashboard), or automatic from a breached hard limit (max drawdown, daily loss
  catastrophic, reconciliation mismatch from the ledger, data-feed loss).
- **Behavior when tripped:** pre-trade pipeline step 2 short-circuits to `block`; emits
  `risk.kill_switch(tripped)`; optionally submits cancels for all open orders (never force-closes positions in
  paper without explicit policy).
- **Durability:** kill-switch state is an event-sourced aggregate (`risk.kill_switch` events) so it survives
  restart and is auditable (who tripped/reset, when, why). Default-safe: an unknown/indeterminate state is
  treated as tripped.

---

## 5. Circuit breakers

Automatic, *temporary*, self-resetting halts (distinct from the manual kill switch).

- **Types:** per-instrument (price move / vol spike / feed gap), per-portfolio (drawdown, daily-loss soft cap),
  market-wide (index move mirroring NSE/BSE index-based halts), execution-anomaly (fill rate/slippage far from
  model → halt & alert).
- **Mechanism:** breaker has `armed → tripped(cooloff_until) → half_open → armed`. While tripped, new
  risk-increasing orders in scope are blocked; at `cooloff_until` it goes `half_open` (allow a limited probe),
  and returns to `armed` if conditions normalized, else re-trips with backoff.
- Emits `risk.circuit_breaker` events; surfaced on the dashboard and via alerts.

---

## 6. Risk snapshot & data model

**RiskSnapshot** (immutable, built once per pre-trade evaluation): portfolio equity, peak equity, available/
reserved cash, open positions & exposures, sector/cluster rollups, today's realized/unrealized P&L, per-
instrument vol/ATR, active breaker/kill states, and the config version. Built from projections (ledger balance,
positions, metrics) — never recomputed from raw events on the hot path.

Tables (all `[NEW]`, design-only):
- `risk_limits` — versioned config: `id, scope(global|portfolio|strategy|instrument), scope_id, limit_type,
  params(JSON), effective_from, is_active`.
- `risk_events` — append-only per-rule evaluations + verdicts (also flows to `event_store`).
- `risk_state` — current kill-switch / breaker state per scope (projection, rebuildable from events).
- `risk_snapshots` — optional persisted snapshots for audit/replay of a specific decision.

Config is **versioned and effective-dated**; a decision records which `risk_limits` version it used, so a past
verdict is fully reproducible.

---

## 7. Integration & failure behavior
- **OMS coupling:** synchronous, in-process call on the order path; returns a signed verdict token. Continuous
  rules subscribe to `portfolio.updated`/`metrics.updated`.
- **Backtest/replay:** the *same* rule code runs in the backtester (shared engine), so live and backtested risk
  behavior are identical — no "risk drift" between simulation and paper.
- **Fail-closed everywhere:** snapshot failure, missing config, rule exception, or stale data (age > threshold)
  ⇒ block + alert. Availability of the gate is a hard dependency of the order path.
- **Determinism:** all time via Clock; all money via Decimal; no randomness in rules.

---

## 8. Review checkpoint
Per the approval, **implementation pauses for review before the Risk Engine is built**. This document is the
artifact for that review. Open design questions to settle at that gate: (a) strict-block vs size-reduction
default per rule; (b) auto-cancel vs leave-open on kill-switch trip in paper; (c) correlation-window length &
recompute cadence; (d) which limits are hard (kill switch) vs soft (circuit breaker) by default.
