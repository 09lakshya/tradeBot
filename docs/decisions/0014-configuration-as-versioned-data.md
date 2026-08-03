# ADR 0014 — Configuration as versioned data

**Status:** Accepted (2026-08-02). Additional decision 3 of the design-package approval.

## Context

Risk limits, fees/charges, thresholds, and strategy parameters change over time and directly affect trading
outcomes. Hardcoding them makes changes invisible, unauditable, and impossible to reproduce historically —
unacceptable for a system that must replay any past session exactly (ADR 0013).

## Decision

Configuration is **versioned data**, never hardcoded:
- Risk limits, cost/fee profiles, thresholds (MTM cadence, reconciliation interval, rate limits, performance
  SLOs), and strategy parameters live in effective-dated, append-only DB tables. A change writes a **new
  version row**; old rows persist for replay.
- **`config_snapshots`** are immutable, addressable bundles of the active configuration; trades/sessions pin a
  `config_snapshot_id` so configuration cannot drift mid-session.
- Every change is **timestamped, attributed, and audited** (`config.changed` event → security/audit log),
  **validated** before activation (rejected if invalid), and **atomically activated** as a new snapshot.
- **No business constants in code** — a typed, validated loader reads them at runtime.
- Rollback = activate a prior snapshot (immutable, lossless, audited). Day-zero defaults ship as a seeded,
  versioned snapshot.

Full design in `docs/design/reproducibility-and-configuration.md` §3.

## Consequences

- (+) Every configuration change is auditable and reversible; historical sessions replay with the exact config
  in force at the time.
- (+) Operators tune limits/thresholds without code deploys, safely (validation + snapshot pinning).
- (−) A config store, loader, validation, and snapshot machinery to build; no business literals allowed —
  enforced by review and lint checks.

## References
`docs/design/reproducibility-and-configuration.md`, ADR 0013, `docs/design/risk-engine.md` (risk_limits),
`docs/design/oms-paper-trading-core.md` (cost_profiles), `docs/design/security.md` (audit).
