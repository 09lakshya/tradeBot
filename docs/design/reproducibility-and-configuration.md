# Reproducibility, Versioning & Configuration — Technical Design

**Status:** Approved design (design-only) · **Phase:** Design-only · **Date:** 2026-08-02
**Locks:** Additional decisions 1 (Deterministic Replay), 2 (Version Everything), 3 (Configuration Management).
**Becomes:** ADR 0013 (replay + version-everything) and ADR 0014 (config-as-data).
**Depends on:** ADR 0008 (event sourcing), ADR 0009 (Clock/Decimal), `event-schemas.md`, `ledger-architecture.md`.

> These three decisions together make **"why did this trade happen, exactly, and can I reproduce it bit-for-bit"**
> a structural property of the platform rather than a best-effort afterthought.

---

## 1. Deterministic replay (Decision 1)

Replay is a **first-class capability**, not a debugging convenience. Any paper-trading session is reproducible
from a fixed set of pinned inputs, and replay reproduces **identical OMS behavior** (same orders, fills,
ledger postings, positions, portfolio, risk verdicts).

### 1.1 The reproducibility 6-tuple
A session is fully determined by:
```
ReplayManifest = {
  data_snapshot_id,     # exact market-data version (instrument set + bars + adjustment state)
  event_log_range,      # [from_seq, to_seq] of the append-only event store for the session
  strategy_version_id,  # immutable strategy version (code + params ref)
  model_version_id,     # immutable model artifact (nullable for non-ML strategies)
  config_snapshot_id,   # versioned risk/cost/threshold/param snapshot (§3)
  seed,                 # RNG seed for any stochastic component (slippage, sampling)
}
```
Given the manifest, `ReplayEngine` sets the Clock to `replay` mode (ADR 0009), folds the event log through the
**same handlers used online**, and asserts the reconstructed state equals the recorded state.

### 1.2 Why it is deterministic
- **Time** comes only from the Clock (ReplayClock advances to each event's `occurred_at`) — no wall-clock reads.
- **Money/quantities** are fixed-point Decimal — no float non-determinism.
- **Randomness** is seeded per `(order_id, fill_seq)` and recorded in the manifest.
- **Handlers are pure** over `(event, current state, config)` — no hidden I/O, no ambient state.
- **Inputs are pinned** — data snapshot + config snapshot + strategy/model versions are immutable.

### 1.3 Modes (same code path)
| Mode | Clock | Data source | Use |
|---|---|---|---|
| Live paper | SystemClock | live feed | normal operation |
| Replay | ReplayClock | recorded event log + data snapshot | bug repro, audit, AI-decision replay |
| Backtest/Sim | SimClock | historical bars | strategy validation (ADR 0012) |

### 1.4 Verification
A `replay_verifies(session_id)` check re-runs the manifest and byte-compares the reconstructed projections
(orders, positions, ledger trial balance, portfolio) against the stored ones. This is a CI/monitoring gate:
**a session that does not replay identically is a correctness bug**, surfaced like a failed reconciliation.

---

## 2. Version everything (Decision 2)

Every **trade** (and every risk verdict and every posting) references **immutable versions** of everything that
influenced it, so the full causal context of any historical decision is recoverable forever.

### 2.1 Versioned entities
| Entity | Version table | Immutable? | Pinned by |
|---|---|---|---|
| Strategy | `strategy_versions` | yes (new row per change) | orders, signals |
| Model | `model_versions` | yes (content-addressed artifact) | signals (ML) |
| Cost profile | `cost_profiles` (already designed) | yes (effective-dated) | fills, ledger postings |
| Risk profile | `risk_limits` versions (already designed) | yes (effective-dated) | risk verdicts |
| Market-data provider | `provider_versions` | yes (provider id + config hash) | bars / data snapshot |
| Feature set | `feature_set_versions` | yes (definition hash) | signals (ML) |
| Configuration | `config_snapshots` (§3) | yes | everything above |

### 2.2 Trade provenance record
Every order carries a **provenance stamp** (immutable, copied onto the order at creation):
```
OrderProvenance = {
  strategy_version_id, model_version_id?, feature_set_version_id?,
  cost_profile_id, risk_profile_version_id, provider_version_id,
  config_snapshot_id, data_snapshot_id?, correlation_id
}
```
Stored on the order (and echoed in `order.created` event payload). Fills inherit it; ledger postings link to it
via `correlation_id`. Result: from any single trade you can reconstruct *exactly* which strategy logic, model,
costs, risk limits, feature definitions, provider, and config produced it — and replay it (§1).

### 2.3 Immutability rules
- Version rows are **append-only**; a "change" creates a new version id, never mutates an existing one.
- Artifacts (models, feature definitions) are **content-addressed** (hash = id) so identical content dedupes and
  tampering is detectable.
- Nothing that a trade points to can ever change under it — the pointer is stable for all time.

---

## 3. Configuration management (Decision 3)

Configuration is **versioned data**, never hardcoded. Risk limits, fees/charges, thresholds, and strategy
parameters live in the database as effective-dated, timestamped, auditable records.

### 3.1 Model
- **`config_snapshots`** — an immutable, addressable bundle of the active configuration at a point in time:
  `id, created_at, created_by, description, contents (refs to the specific versioned config rows), hash`.
  A session/trade pins a `config_snapshot_id`; the snapshot pins the exact `cost_profile`, `risk_limits`,
  strategy-param, and threshold versions in force.
- **Domain config tables** (already partly designed): `cost_profiles`, `risk_limits`, `strategy_params`,
  and a general `app_config` for operational thresholds (MTM cadence, reconciliation interval, rate limits).
  All are **effective-dated** (`effective_from`, `is_active`) and **append-only versioned** — a change writes a
  new row; the old row remains for historical replay.

### 3.2 Change discipline
- **No hardcoded business constants.** Charges, limits, thresholds, cadences, and parameters are read from the
  config store at runtime (with a typed, validated loader), never literals in code.
- **Every change is timestamped + attributed + audited** (who, when, why) and emits a `config.changed` event
  → security/audit log (see `security.md`, `monitoring-observability.md`).
- **Atomic activation:** flipping the active config produces a new `config_snapshot`; in-flight sessions keep
  their pinned snapshot (no mid-session drift), new sessions pick up the new one.
- **Validation before activation:** a config change is schema-validated and dry-run against invariants (e.g.
  risk limits internally consistent, cost profile complete) before it can become active. Bad config is rejected,
  not silently applied.
- **Rollback:** because snapshots are immutable and addressable, reverting is "activate the prior snapshot" —
  fully auditable, no data loss.

### 3.3 Bootstrapping
Defaults ship as an initial seeded `config_snapshot` (a migration/seed, itself versioned), so a fresh
environment is reproducible and the "day-zero" configuration is auditable like any later change.

---

## 4. How the three decisions interlock
```
config_snapshots ─┐
strategy_versions ─┤
model_versions ────┼─▶ OrderProvenance (on every order) ─▶ event log ─▶ ReplayManifest ─▶ identical replay
cost/risk versions ┤
provider/feature ──┘
```
Version-everything supplies the immutable pointers; config-as-data makes one of those pointers (configuration)
first-class and auditable; deterministic replay consumes all of them to reproduce any session exactly. None of
the three is sufficient alone; together they deliver complete, reproducible auditability.

---

## 5. Implementation checklist (when the PG gate passes)
1. Add `strategy_versions`, `model_versions`, `feature_set_versions`, `provider_versions`, `config_snapshots`
   (append-only, content-addressed where noted) via expand migrations.
2. Add `OrderProvenance` columns/embed to `orders`; echo in `order.created` payload.
3. Implement the typed config loader (no business literals in code) + `config.changed` audit event.
4. Implement `ReplayEngine` + `replay_verifies()` and wire it as a CI/monitoring gate.
5. Parity tests: a recorded paper session replays byte-identically; a config change mid-stream does not affect
   an already-pinned session.
