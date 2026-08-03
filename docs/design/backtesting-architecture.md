# Backtesting Architecture — Technical Design

**Status:** Approved design (design-only) · **Phase:** Design-only · **Becomes:** ADR 0012 (shared execution).
**Depends on:** OMS design (shared Fill/Cost engine), Risk design (shared rules), Market Data Layer, ADR 0005.

> Core principle: the backtester is **not a separate simulator**. It reuses the OMS Execution Engine, Cost
> Engine, and Risk Engine behind the `ExecutionVenue` interface, driven by a **replay Clock** over historical
> bars. This guarantees backtest ≡ paper ≡ (future) live behavior — the single most important defense against
> the "backtester lies" failure mode flagged in the key-challenges memory.

---

## 1. Event-driven engine

- **Architecture:** a single-threaded, deterministic event loop over a time-ordered event queue. No vectorized
  look-ahead shortcuts on the decision path (vectorization is allowed only for indicator precompute that is
  strictly causal).
- **Event types on the queue:** `MarketBar`, `MarketTick` (if intraday), `SignalDue`, `OrderEvent`,
  `FillEvent`, `TimerEvent` (MTM cadence, session open/close), `CorporateActionEvent`.
- **The loop:** pop earliest event by `(timestamp, priority)` → advance Clock to it → dispatch to the relevant
  engine (strategy / OMS / risk / portfolio) → any resulting events are enqueued with `timestamp ≥ now`.
- **Look-ahead prevention (the cardinal rule):** a strategy at time `t` may only read data with
  `timestamp ≤ t`. Enforced structurally: the market-data accessor handed to strategies is a
  **point-in-time view** bounded by the Clock; requesting future data raises. Signals generated on bar `t`
  can only fill on bar `t+1` open (or intrabar per fill model), never on `t`'s close it was computed from.
- **Determinism:** Clock-driven time, seeded randomness per `(order_id, fill_seq)`, ordered event queue ⇒ a
  run is byte-reproducible from `(data snapshot, config, seed)`. Same inputs ⇒ same equity curve.

---

## 2. Fill simulation (shared with OMS)

Reuses the OMS Fill Engine (`oms-paper-trading-core.md` §5) via `ExecutionVenue`:
- **Marketability** from the bar (limit crosses `low`/`high`; stop triggers on breach), partial & multiple
  fills, participation cap vs bar volume, illiquid/zero-volume bars don't fill (a real Yahoo finding).
- **Fill price model** (configurable, conservative defaults): market orders fill at next-bar open ± slippage;
  limits at limit price or better (price improvement when the bar gaps through); stops convert to market on
  trigger. **Next-bar-open default** avoids the classic "fill at the close you used to decide" leak.
- **Latency simulation:** configurable order→exchange delay shifts eligibility by N bars/ms.

## 3. Cost simulation (shared Cost Engine)

Reuses the OMS Indian Cost Model (§6): brokerage, STT, GST, exchange txn charges, SEBI, stamp duty, DP
(reserved). Same versioned `cost_profiles` as paper, so backtested net returns match paper net returns for the
same fills. Costs post through the **same double-entry ledger** in backtest runs (isolated per-run portfolio),
so backtest P&L is computed by the identical accounting path — not a parallel approximation.

## 4. Slippage

- Models (configurable, per instrument/liquidity): fixed bps, spread-proportional, volume-participation
  (square-root market impact `k·σ·√(qty/ADV)`), and a worst-case bound for stress runs.
- Slippage is seeded and deterministic; booked to the memo slippage account (ledger `5800`) so its total cost
  contribution is explicit in results.
- Default is deliberately **pessimistic** — the project's stance is that an over-optimistic backtest is worse
  than a conservative one.

---

## 5. Walk-forward validation

The primary defense against overfitting (key-challenges memory).

- **Rolling/anchored windows:** train (in-sample) → validate (out-of-sample) → step forward; repeat across the
  history. Anchored (expanding) and rolling (fixed) both supported.
- **Optimization only on in-sample**, evaluation only on the untouched out-of-sample slice; the concatenation
  of OOS slices is the honest performance estimate.
- **Purging & embargo:** remove samples whose label horizon overlaps the train/test boundary, plus an embargo
  gap, to kill leakage from overlapping windows (López de Prado method).
- **Combinatorial purged CV** available for a distribution of OOS paths rather than a single split.
- Every window's config, seed, and metrics are stored so the walk-forward is fully reproducible and auditable.

## 6. Monte Carlo

- **Trade-order resampling / bootstrap:** resample the sequence of trade returns to build a distribution of
  terminal equity, max drawdown, and ruin probability — exposes path-dependency and luck.
- **Parametric & block bootstrap** on returns (block preserves autocorrelation).
- **Randomized execution perturbation:** jitter slippage/fill timing within model bounds to test robustness to
  microstructure assumptions.
- **Synthetic paths** (optional): regime-preserving surrogate series to stress strategies beyond the single
  realized history.
- Outputs: confidence intervals on CAGR/Sharpe/maxDD, P(ruin), and a robustness score used in promotion gates.

---

## 7. Performance metrics

Computed by the **same metrics domain** used live (single source of truth), from the equity curve + trade log:
- Returns: total, CAGR, per-period; **net of the full Indian cost model**.
- Risk-adjusted: Sharpe, Sortino, Calmar, MAR.
- Drawdown: max, average, duration, recovery; underwater curve.
- Trade stats: win rate, profit factor, expectancy, avg win/loss, exposure/turnover, tail ratio.
- Capacity/liquidity: turnover vs ADV, implied capacity ceiling.
- Benchmark-relative: alpha/beta vs NIFTY/sector, tracking error, information ratio.
- **Statistical significance:** deflated Sharpe ratio & PBO (probability of backtest overfitting) reported
  alongside raw metrics so a pretty curve can't be promoted on noise.

---

## 8. Result storage

- **`backtest_runs`** — `id, strategy_id, params_ref, data_snapshot_id, code_version, seed, cost_profile_id,
  window_spec, created_at, status`. Immutable once complete.
- **`backtest_metrics`** — per-run and per-window metric rows.
- **`backtest_trades`** / **`backtest_equity`** — full trade log and equity curve (hypertable for equity).
- **`data_snapshots`** — pins the exact market-data version used (instrument set + adjustment state), so a run
  is reproducible even as the live data evolves. Reuses the market-data validation/checkpoint machinery.
- **Reproducibility contract:** `(data_snapshot_id, code_version, params, seed, cost_profile)` fully determines
  a run's results; storing these lets any run be re-executed and byte-compared (CI regression guard).
- Results feed the AI research layer (`ai-research-architecture.md`) as the objective/evaluation signal and the
  experiment-tracking record.

---

## 9. Correctness safeguards (why this backtester can be trusted)
| Failure mode | Structural defense |
|---|---|
| Look-ahead bias | point-in-time data view bounded by Clock; signals fill on next bar |
| Survivorship bias | full discovered universe incl. delisted (market-data discovery, ADR 0004) |
| Adjustment leakage | prices pre-adjusted correctly upstream (ADR 0005); backtester never re-adjusts |
| Cost optimism | shared, versioned Indian cost model; pessimistic slippage defaults |
| Sim/live drift | shared Execution + Cost + Risk engines via `ExecutionVenue`; not a separate simulator |
| Overfitting | walk-forward + purge/embargo + Monte Carlo + deflated Sharpe/PBO gates |
| Irreproducibility | pinned data snapshot + code version + seed; results re-runnable & CI-compared |

This document becomes ADR 0012 (backtester reuses the OMS execution/cost/risk engines as the single source of
truth). Implementation is sequenced **after** OMS + Risk are built and reviewed.
