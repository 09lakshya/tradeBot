# Database Migration Plan — Technical Design

**Status:** Approved design · **Phase:** Design-only (no migrations authored yet) · **Tooling:** Alembic +
SQLAlchemy, PostgreSQL 16 + TimescaleDB. **Depends on:** ADR 0002 (TimescaleDB), OMS/ledger designs.

> Scope guard: this is the *policy and procedure* for migrations. The actual OMS migration files are written
> only after the PG/TimescaleDB validation gate passes.

---

## 1. Migration strategy

### 1.1 Tooling & structure
- **Alembic** is the single source of schema truth; `alembic.ini` + `backend/alembic/versions/*` already exist
  (baseline `0001_initial_schema`). Every schema change is a reviewed, versioned migration — **no manual DDL**
  in any environment.
- **One logical change per migration.** A migration does exactly one conceptual thing (add table, add column,
  backfill, add constraint). Large features are a *sequence* of small migrations, not one mega-migration.
- **Naming:** `NNNN_short_slug.py`, monotonically increasing, linear history (no unmerged branches on `main`).
- **Hypertables & policies** (OHLCV, equity_snapshots, and new append-only ledger/event tables) are created
  via `create_hypertable(...)` **inside** the migration, immediately after `create_table`, with the partition
  column present in the PK (validated by `test_pg_infrastructure.py`). Compression/retention policies are their
  own later migrations so they can be tuned independently.

### 1.2 Expand → migrate → contract (the core pattern)
Every potentially-breaking change is split across **three deploys** so the running app is always compatible
with the schema on both sides of the change:

1. **Expand** — add the new shape *additively* (new nullable column / new table / new enum value). Old code
   ignores it; new code can write it. Never remove or rename in this step.
2. **Migrate/backfill** — dual-write from app code (or a one-shot idempotent backfill job) to populate the new
   shape; verify parity with a reconciliation query.
3. **Contract** — once no code reads the old shape, drop it (old column/table/enum value) in a later deploy.

This is how the `transactions` (single-entry) → `ledger_entries` (double-entry) change and the `OrderStatus`
enum expansion (`partial → partially_filled`) are done without downtime (§3, §4).

### 1.3 Enum evolution (Postgres native enums)
- **Adding** a value: `ALTER TYPE ... ADD VALUE` — safe, online, but *cannot run inside a transaction block* on
  older PG and cannot be removed. For the lifecycle expansion, add `created, validated, accepted,
  partially_filled, expired` as new values first (expand), migrate rows off `partial`, keep `partial` as a
  tolerated alias until contract.
- **Removing/renaming** a value requires the type-swap dance: create `order_status_v2`, `ALTER COLUMN ... TYPE
  order_status_v2 USING (...)`, drop old type, rename. Done only in the contract phase, gated on zero readers.
- Preferred long-term: application-level enums stored as `text` + `CHECK`, which evolve without type swaps.
  Decision for OMS: keep native enums for the closed, stable sets (order_type) and use `text+CHECK` for sets we
  expect to extend (status), documented in the OMS migration ADR.

---

## 2. Rollback strategy

- **Every migration has a real `downgrade()`** that is tested. CI runs `upgrade head` → `downgrade base` →
  `upgrade head` on a scratch PG (already asserted by `test_pg_infrastructure.py`'s alembic cycle test).
- **Additive migrations** (expand) have trivial, lossless downgrades (drop the added object).
- **Destructive migrations** (contract: drop column/table) are the risky ones. Policy:
  - They run **only** after a bake period where the removed object is provably unused (logs/metrics show zero
    reads), so a rollback would just re-add an empty object.
  - Before the drop, a `pg_dump` of the affected table(s) is taken and archived; the downgrade restores
    structure, and the archived dump restores data if truly needed.
  - Data-lossy downgrades are explicitly labeled `# IRREVERSIBLE DATA LOSS` and require a runbook note.
- **Backfill migrations** are **idempotent and re-runnable** (upsert / `WHERE new_col IS NULL`), so a partial
  failure is resumed by re-running, and a downgrade simply nulls the derived column.
- **Failure handling:** migrations run in a transaction where possible; DDL that can't be transactional
  (concurrent index, enum add) is isolated in its own migration so a failure doesn't leave a half-applied txn.

---

## 3. Zero-downtime approach

The app is a modular monolith (ADR 0001); zero-downtime means **schema and running code are always mutually
compatible**. Rules:

1. **Never break the currently-deployed app with a migration.** Migrations deploy *before* the code that needs
   them (expand), or *after* the code that stopped needing them (contract).
2. **Additive-online DDL only during business hours.** `CREATE INDEX CONCURRENTLY`, `ADD COLUMN` (nullable, no
   volatile default), `ADD VALUE` to enum — all non-locking. Volatile/`NOT NULL` defaults are added in two
   steps (add nullable → backfill → set `NOT NULL` with `NOT VALID` then `VALIDATE CONSTRAINT`) to avoid full
   table rewrites/locks.
3. **Long backfills run as chunked background jobs** (Celery), batched by PK range with throttling, not inside
   the migration transaction — the migration only creates the target column/table.
4. **Constraints added `NOT VALID` first**, validated in a separate step that takes only a `SHARE UPDATE
   EXCLUSIVE` lock, avoiding a blocking full scan.
5. **Hypertable creation** on an empty new table is instant; converting a populated table is avoided by
   creating append-only tables as hypertables from the start.
6. **Deploy ordering is enforced** by a release checklist: `alembic upgrade` step is a distinct, ordered stage
   in the deploy pipeline relative to the app rollout, per the expand/contract phase of the change.

Because this phase is greenfield (no production rows), the *first* OMS migration set can create the target
shape directly — but the plan above governs every change **after** first production data exists, which is the
regime that matters.

---

## 4. Versioning policy

- **Schema version = Alembic head revision.** `alembic current` is the deployed schema version; recorded in
  `/health/ready` output and release notes.
- **Linear, forward-only history on `main`.** No editing a migration after it has run anywhere shared; fixes
  are *new* migrations. Squashing is allowed only pre-first-production (greenfield window) and is itself a
  documented event.
- **App ⇄ schema compatibility window:** the app supports **N and N-1** schema shapes during any expand/
  contract cycle, so a rollback of the app one version never hits an incompatible schema.
- **Event-schema versioning** (separate concern, see `event-schemas.md`): stored events are versioned per type
  with upcasters; DB migrations never rewrite stored events — replay compatibility is preserved by upcasting at
  read time.
- **Migration ↔ ADR link:** any migration that changes a decision recorded in an ADR references it in the
  docstring; new architectural shapes get a new ADR before the migration merges.

---

## 5. Future schema evolution

| Anticipated change | Approach |
|---|---|
| New order types (bracket/OCO/iceberg) | `order_groups` hooks already reserved; additive columns + new enum values (expand-only) |
| Short-selling / margin | new accounts in ledger chart (additive), `positions.direction` already present, margin tables `[NEW]` additive |
| Live broker connectivity | new `ExecutionVenue` rows + broker-mapping tables; no change to core OMS tables (venue behind interface) |
| Multi-currency | `currency` columns already present (fixed `INR` now); FX-rate table + revaluation postings additive |
| Partitioning growth | TimescaleDB chunk interval tuning + compression/retention policies as standalone migrations |
| Read-scaling | add read replicas; no schema change (monolith already isolates domains for future extraction) |
| Analytics/warehouse | CDC/outbox → warehouse; source schema unaffected (outbox already the integration seam) |

**Evolution principles:** additive-first, expand/migrate/contract for anything breaking, hypertables for any
new high-volume append-only stream, and every high-volume table designed append-only from day one so history
is never mutated (aligns with the ledger + event-sourcing mandates).

---

## 6. Pre-implementation checklist (executed when the PG gate passes)
1. Confirm baseline `0001` applies cleanly to the validated cloud PG.
2. Author OMS migrations as an ordered expand sequence: `accounts` → `postings`/`ledger_entries` (hypertable) →
   `event_store`/`order_events` (hypertable) → `oms_outbox` → `orders` refine → `fills` refine →
   `position_lots` → `order_groups` → `cost_profiles` → projections (`cash_balances`, etc.).
3. Each migration ships with `downgrade()` + a targeted integration test (marked `postgres`).
4. Run the full `upgrade → downgrade → upgrade` cycle in CI against cloud PG before merge.
5. Only then begin OMS service code against the migrated schema.
