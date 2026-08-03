# AI / Strategy Research Architecture — Technical Design

**Status:** Approved design (design-only) · **Phase:** Design-only · **Sequencing:** this is the **LAST** layer
built, only after data → OMS → risk → strategy → backtester → metrics are trustworthy (ADR 0011,
correctness-first). **Depends on:** backtesting architecture (objective signal), model registry conventions.

> Guiding principle: AI never trades directly. It **proposes** strategies/parameters; every proposal is
> validated by the same walk-forward + Monte Carlo gates as any human strategy and must pass the Risk Engine
> in paper before it ever influences a live decision. The research loop is a *candidate generator*, not an
> autonomous trader. This containment is the core safety property.

## 0. AI Isolation (locked decision, ADR 0015)

**The AI Research Engine must never directly place orders.** This is a hard architectural boundary, enforced
structurally — not a policy that could be relaxed by configuration.

- **Permitted responsibilities, exhaustively:** strategy **discovery**, **optimization**, **evaluation**, and
  **recommendation** (producing candidate strategy versions with metrics).
- **Forbidden:** any path from the research engine to `order.submitted`, to the OMS, or to the execution venue.
  The research engine has **no dependency on and no handle to** the OMS/Execution layer — it cannot call it.
- **The only interface out of research is the strategy registry.** Research writes **candidate** strategy
  versions; the Paper Trading Engine consumes **only approved/promoted** versions (candidate → validated →
  paper → human-approved live, §5). An unapproved version is invisible to the trading path.
- **Enforcement:** module boundaries (research domain does not import the trading/execution domain), the
  registry `status` gate (only `paper`/`live` versions are loadable by the OMS), and the mandatory Risk gate +
  human approval before any live influence. Even a compromised or buggy research loop cannot emit an order.

---

## 1. Layered pipeline

```
   ┌─ Search space (features, rules, hyperparameters) ─┐
   │                                                   │
Discovery ─▶ Optimization ─▶ Backtest eval ─▶ Validation gates ─▶ Registry ─▶ Promotion ─▶ Paper ─▶ (Live)
   ▲                                                   │                                    │
   └──────────────── experiment tracking ─────────────┴──────── rollback ◀─────────────────┘
```

Every arrow's inputs/outputs are recorded in experiment tracking; every promotion/rollback is an audited,
event-sourced decision.

---

## 2. Strategy discovery

- **Feature library:** causal, point-in-time features from the market-data layer (technical, cross-sectional,
  regime, calendar). All features carry the same look-ahead guarantees as the backtester.
- **Search modes:**
  - **Parametric search** over a fixed strategy template's rule thresholds.
  - **Structural/genetic search** that composes rule trees (entries/exits/filters) from primitives.
  - **ML predictors** (sklearn/XGBoost/LightGBM per the locked stack) producing signals consumed by a fixed
    execution template — the model outputs a score, the template turns scores into orders.
- **Guardrails:** search space is registered & versioned; every candidate is fingerprinted (config hash) to
  detect duplicates and enable caching; a complexity penalty discourages over-parameterized candidates.

## 3. Hyperparameter optimization

- **Optuna** (locked stack) as the orchestration layer with pluggable samplers.
- **Objective:** a robust, overfit-aware score from the backtester — e.g. OOS deflated Sharpe penalized by PBO
  and drawdown — **not** in-sample return. The objective is computed only on walk-forward OOS slices.
- **Pruning:** early-stop unpromising trials (median/Hyperband pruner) on partial walk-forward windows.
- **Parallelism:** trials run as Celery tasks against a shared Optuna storage (the production PG), each trial a
  reproducible backtest run (pinned data snapshot + seed).

### 3.1 Bayesian optimization
- TPE / GP-based samplers (via Optuna) for sample-efficient search of expensive backtest evaluations.
- Acquisition balances exploration/exploitation; priors seeded from prior studies on the same template.

### 3.2 Genetic algorithms
- For structural search (rule-tree composition) where the space is combinatorial/non-differentiable.
- Population of candidate strategies; fitness = the same robust OOS objective; crossover/mutation on rule
  primitives; elitism + diversity pressure to avoid premature convergence on one overfit lineage.

### 3.3 Reinforcement learning (deferred, contained)
- **Deferred** per the locked stack (PyTorch/LSTM postponed); documented here for the search space, not built
  early. When introduced: RL agent acts in the **replay/paper environment only** (the OMS as a Gym-like env
  driven by the replay Clock), reward = risk-adjusted, cost-inclusive P&L from the real accounting path.
- Same containment: an RL policy is just another candidate that must clear validation + paper before any live
  influence; it is never wired to live order submission by the training loop.

---

## 4. Model & strategy registry

- **`strategy_registry`** — every candidate/version: `id, lineage_id, template, params_ref, feature_set_ref,
  code_version, data_snapshot_id, status(candidate|validated|paper|live|retired|rejected), metrics_ref,
  created_at`.
- **`model_artifacts`** — serialized models (XGBoost/LightGBM boosters, sklearn pipelines) with hash,
  training-data snapshot, and metrics; storage is content-addressed and immutable.
- **Lineage:** each version links to its parent (which study/generation produced it), giving a full genealogy
  of how a strategy evolved — essential for auditing AI decisions.
- **Reproducibility:** a registry entry pins everything needed to re-run (code, params, data snapshot, seed),
  so any promoted strategy can be re-validated from scratch.

## 5. Strategy promotion

A **staged, gated** lifecycle — no jump straight to live:

```
candidate ─(validation gates)─▶ validated ─(paper trading N days)─▶ paper-proven ─(human approval)─▶ live
```

- **Validation gates (automatic, all must pass):** walk-forward OOS performance ≥ thresholds; PBO below cap;
  deflated Sharpe significant; Monte Carlo ruin probability below cap; capacity ≥ requirement; risk-limit
  compatibility (the strategy's typical order sizes pass the Risk Engine).
- **Paper stage:** promoted to live-paper trading through the real OMS + Risk gate for a minimum period;
  live-paper results are compared to the backtest's out-of-sample expectation (drift detection).
- **Human approval** is required for the final paper→live transition (kept as a control even in the "autonomous"
  vision). Promotion decisions are event-sourced (`strategy.promoted`) and reversible.

## 6. Rollback

- **Every promotion is reversible.** `strategy.rollback` demotes a version (live→paper→disabled) and, for live,
  triggers an orderly stand-down (stop new orders; optionally flatten per policy through the OMS).
- **Triggers:** live-vs-backtest performance drift beyond tolerance, risk-limit breaches attributable to the
  strategy, data/feature integrity alerts, or manual intervention / kill-switch.
- **Champion/challenger:** a new version runs as a challenger in paper alongside the incumbent champion;
  rollback is just "keep champion." No in-place mutation of a running strategy — versions are immutable and
  swapped atomically.

## 7. Experiment tracking

- **`experiments`** / **`trials`** tables: study id, sampler, objective, params, seed, data snapshot, all
  metrics, and status — one row per trial, fully queryable.
- Backed by Optuna storage + the backtest result store (§8 of backtesting design); every trial is a
  reproducible backtest run.
- **Dashboards:** study progress, OOS-vs-IS gap (overfit monitor), lineage trees, promotion/rollback timeline.
- **Governance:** the overfit metrics (PBO, IS/OOS gap, number of trials → multiple-testing adjustment via
  deflated Sharpe) are first-class, so the *process* of searching is itself monitored for overfitting, not just
  individual strategies.

---

## 8. Safety & containment summary
| Risk | Control |
|---|---|
| AI overfits and looks great in-sample | robust OOS objective; PBO/deflated-Sharpe gates; walk-forward only |
| AI trades autonomously & badly | AI only *proposes*; Risk gate + paper stage + human approval before live |
| Multiple-testing / data dredging | trial count feeds deflated Sharpe; search process monitored |
| Irreproducible "black box" wins | full lineage + pinned snapshots + seeds in the registry |
| Silent live degradation | live-vs-backtest drift detection → automatic rollback + kill-switch tie-in |
| Look-ahead in features | shared point-in-time feature accessor (same guarantee as backtester) |

Built **last**, on top of a trustworthy core — the sequencing that makes the autonomous vision safe.
