# Double-Entry Ledger Architecture — Technical Design

**Status:** Approved design (implements Decision 1 of the OMS approval, 2026-08-02) · **Phase:** Design-only
**Becomes:** ADR 0007 · **Depends on:** `oms-paper-trading-core.md` §2.5, §12 · PG/TimescaleDB gate before code.

> Scope guard: architecture and contracts only. No migrations, no code in this phase.

---

## 1. Principles (non-negotiable)

1. **Append-only.** Ledger entries are immutable. No `UPDATE`, no `DELETE`, ever.
2. **Double-entry.** Every economic event posts a **balanced journal** — total debits equal total credits.
3. **Derived balances.** No account carries a stored, directly-mutated balance. A balance is *always*
   `SUM(entries)` over its account. Cached projections exist for performance and are rebuildable from entries.
4. **Fixed-point money.** All amounts are `NUMERIC(20, 4)` in the DB and `Decimal` in code. No floats. Currency
   is INR throughout this phase; a `currency` column is present for future-proofing but fixed to `INR`.
5. **Full auditability.** Every entry carries who/what/when/why: timestamp (Clock-sourced UTC), the causing
   event (`correlation_id`/`causation_id`), and the source aggregate (order/fill/corporate-action).
6. **Conservation.** For any `posting_id`, `SUM(signed_amount) = 0`. For the whole book, the accounting
   identity `Assets = Liabilities + Equity` holds at all times (enforced by the balanced-journal invariant).

---

## 2. Account chart

Accounts are typed nodes in a hierarchy. Each has a `normal_balance` (the side that increases it) and a
`class`. Balances roll up the tree. The chart below is the launch set; new accounts are additive.

| Code | Account | Class | Normal | Parent | Notes |
|------|---------|-------|--------|--------|-------|
| `1000` | **Assets** | asset | debit | — | root |
| `1100` | Cash & settlement | asset | debit | 1000 | |
| `1110` | Cash — available | asset | debit | 1100 | spendable buying power source |
| `1120` | Cash — reserved (BP hold) | asset | debit | 1100 | funds held for `accepted` orders (§5.4) |
| `1130` | Settlement receivable | asset | debit | 1100 | T+1 sale proceeds in transit (future) |
| `1200` | **Securities** | asset | debit | 1000 | position market value carrier (contra to equity MTM) |
| `1210` | Securities at cost | asset | debit | 1200 | cost basis of open lots |
| `2000` | **Liabilities** | liability | credit | — | root |
| `2100` | Settlement payable | liability | credit | 2000 | T+1 purchase obligations (future) |
| `2200` | Charges payable | liability | credit | 2000 | accrued but unsettled charges (paper: settles instantly) |
| `3000` | **Equity** | equity | credit | — | root |
| `3100` | Opening capital | equity | credit | 3000 | initial funding of a portfolio |
| `3200` | Contributions / withdrawals | equity | credit | 3000 | cash added/removed by the user |
| `3300` | Retained P&L | equity | credit | 3000 | closes from realized P&L + expenses at EOD |
| `4000` | **Income** | income | credit | — | root (nominal; closes to 3300) |
| `4100` | Realized trading P&L | income | credit | 4000 | gain on lot closure |
| `4200` | Dividend income | income | credit | 4000 | cash dividends received |
| `5000` | **Expenses** | expense | debit | — | root (nominal; closes to 3300) |
| `5100` | Brokerage | expense | debit | 5000 | |
| `5200` | STT (securities transaction tax) | expense | debit | 5000 | |
| `5300` | Exchange transaction charges | expense | debit | 5000 | |
| `5400` | GST | expense | debit | 5000 | on brokerage + txn charges |
| `5500` | SEBI charges | expense | debit | 5000 | |
| `5600` | Stamp duty | expense | debit | 5000 | buy-side |
| `5700` | DP charges | expense | debit | 5000 | reserved (delivery/demat, future) |
| `5800` | Slippage (memo) | expense | debit | 5000 | modeled execution cost, paper-only memo account |

**Sub-ledger dimension.** Position-level detail (per instrument, per lot) is *not* modeled as separate GL
accounts — that would explode the chart. Instead every entry carries optional `instrument_id` and
`related_fill_id` dimensions; position value and per-instrument cost roll up by grouping on those dimensions.
`positions`/`position_lots` (OMS design §8) are the authoritative sub-ledger and must reconcile to `1210`.

---

## 3. Journal entry format

A **posting** is one balanced journal (the atomic unit). It contains ≥2 **entries**.

```
Posting
  posting_id        UUID                -- groups the balanced set
  event_type        enum                -- trade|brokerage|stt|gst|stamp_duty|exchange|sebi|dp
                                         --   |dividend|corp_action|opening|contribution|withdrawal|adjustment|pnl_close
  portfolio_id      UUID (FK)
  occurred_at       TIMESTAMPTZ         -- business time (Clock), UTC
  recorded_at       TIMESTAMPTZ         -- wall-clock insert time, UTC
  correlation_id    UUID                -- logical flow (signal→order→fills→postings)
  causation_id      UUID                -- the event that directly caused this posting
  source_ref        JSON                -- {order_id, fill_id, corporate_action_id, ...}
  memo              text
  Entries[] (>=2, SUM(signed_amount)=0)

Entry
  entry_id          UUID
  posting_id        UUID (FK)
  account_code      text (FK -> accounts.code)
  direction         enum(debit|credit)
  amount            NUMERIC(20,4)       -- always positive; sign comes from direction
  signed_amount     NUMERIC(20,4)       -- +amount for debit, -amount for credit (generated column)
  instrument_id     UUID (nullable)     -- sub-ledger dimension
  related_fill_id   UUID (nullable)
  currency          char(3) default 'INR'
  dedup_key         text (unique)       -- idempotency (§6)
```

`signed_amount` uses the **debit-positive** convention uniformly, so `SUM(signed_amount)=0` is the single
balance invariant regardless of account class. A per-account *balance* then applies the account's
`normal_balance` to present a natural positive figure (asset/expense balance = `SUM(signed)`; liability/
equity/income balance = `-SUM(signed)`).

---

## 4. Debit / credit rules (worked)

Convention reminder: **debit** increases assets & expenses; **credit** increases liabilities, equity & income.

### 4.1 Fund a portfolio (opening capital ₹1,000,000)
| Account | Dr | Cr |
|---|---|---|
| 1110 Cash — available | 1,000,000.0000 | |
| 3100 Opening capital | | 1,000,000.0000 |

### 4.2 Reserve buying power on `accepted` (worst-case ₹50,500 for a limit buy)
Move cash from available to reserved. Both are assets, so this is an asset-to-asset transfer (Decision 5).
| Account | Dr | Cr |
|---|---|---|
| 1120 Cash — reserved | 50,500.0000 | |
| 1110 Cash — available | | 50,500.0000 |

### 4.3 Buy fill — 100 @ ₹500 with charges (partial release of reservation)
Reservation was ₹50,500 worst-case; actual notional ₹50,000 + charges ₹23.60. One posting, per-charge entries.
| Account | Dr | Cr | Notes |
|---|---|---|---|
| 1210 Securities at cost | 50,000.0000 | | cost basis of the new lot |
| 5100 Brokerage | 20.0000 | | |
| 5200 STT | 0.0000 | | (delivery buy: STT nil on buy; shown for shape) |
| 5300 Exchange charges | 1.7500 | | |
| 5400 GST | 3.9600 | | 18% on (brokerage+exch) |
| 5500 SEBI charges | 0.0500 | | |
| 5600 Stamp duty | 0.7500 | | buy-side |
| 1120 Cash — reserved | | 50,500.0000 | release the full hold |
| 1110 Cash — available | | -449.4900 | *credit of a negative* = debit ₹449.49 back |

The clean way to express the release+settle is **two entries against reserved and available** plus the
expense/asset legs. Concretely the balanced set is: debit securities+charges (₹50,026.49), debit
`1110` the unused hold (₹473.51), credit `1120` the full reservation (₹50,500.00). Debits
50,026.49 + 473.51 = 50,500.00 = credit. Balanced. (The illustrative negative row above is avoided in
practice; entries always carry positive `amount` with an explicit direction.)

### 4.4 Sell fill closing a lot — 100 @ ₹550, cost ₹500 (FIFO), charges ₹60
| Account | Dr | Cr | Notes |
|---|---|---|---|
| 1110 Cash — available | 54,940.0000 | | proceeds net of charges |
| 5xxx Charges (per class) | 60.0000 | | brokerage/STT/GST/exch/sebi/stamp split |
| 1210 Securities at cost | | 50,000.0000 | remove closed lot's basis |
| 4100 Realized P&L | | 5,000.0000 | (550−500)×100 |

Debits 55,000 = credits 55,000. Realized P&L is booked to income, closed to retained equity at EOD (§4.6).

### 4.5 Cash dividend (₹8/share on 100 shares)
| Account | Dr | Cr |
|---|---|---|
| 1110 Cash — available | 800.0000 | |
| 4200 Dividend income | | 800.0000 |

### 4.6 End-of-day nominal close (income & expense → retained P&L)
Zero out nominal accounts into `3300` so equity reflects the period result and nominal accounts restart at 0.
This is a mechanical closing posting; it never touches asset/liability balances.

### 4.7 Corporate action — 1:2 split (share count doubles, cost basis unchanged)
No cash and no P&L move; the split adjusts **quantity and per-share cost** in the position sub-ledger, not GL
value. A memo posting (`event_type=corp_action`, zero-amount balanced or a metadata-only journal) records the
event for audit and correlation. The authoritative quantity change lives in `position_lots`; the ledger's
`1210` value is unchanged, so no GL entry with a non-zero amount is required. Bonus issues behave the same.
Cash-impacting actions (dividends §4.5, buybacks, special cash) *do* post value entries.

---

## 5. Ledger projections

Projections are **derived, rebuildable** read models. They are never a source of truth.

| Projection | Grain | Refresh | Rebuild source |
|---|---|---|---|
| `cash_balances` | (portfolio, account) | on posting commit (same txn) or async relay | `SUM(signed_amount)` over entries |
| `buying_power` | portfolio | on posting commit | `1110 available` − open reservations |
| `trial_balance` | account | on demand / EOD | `SUM(signed_amount)` grouped by account |
| `position_value` | (portfolio, instrument) | on fill + on mark | lots × mark (OMS §9); reconciles to `1210` cost |
| `pnl_daily` | (portfolio, date) | EOD close | realized (4100) + Δ unrealized + expenses |

**Consistency rule.** A projection write happens in the **same DB transaction** as the posting that changes
it (transactional outbox pattern, OMS §11.2). If a projection is ever suspected wrong, it is dropped and
rebuilt from entries — the entries are canonical, so rebuild is always safe and total.

**Rebuild procedure.** `rebuild_projection(name, portfolio_id?)` truncates the projection rows in scope and
folds every posting (ordered by `occurred_at, posting_id`) through the same pure reducer used online. Because
reducers are pure and entries are immutable, online and rebuilt projections are bit-identical.

---

## 6. Idempotency & concurrency

- **Posting idempotency.** Each entry's `dedup_key` is deterministic:
  `f"{event_type}:{source_ref}:{account_code}:{charge_class|leg}"`. A retried fill produces identical
  `dedup_key`s → unique-constraint conflict → no-op. A fill can therefore be applied "at least once" safely.
- **Ordering.** Postings are totally ordered per portfolio by `(occurred_at, posting_id)`; the balance reducer
  is order-independent for sums but corporate actions and splits are applied in `occurred_at` order.
- **Concurrency.** Balance mutation is serialized per portfolio via the outbox relay (single consumer per
  aggregate) and/or `SELECT ... FOR UPDATE` on the `cash_balances` row; the append of entries itself needs no
  lock (insert-only). Optimistic `event_version` on the aggregate guards concurrent order modifications.

---

## 7. Audit strategy

- **Immutability enforced in depth:** (1) service layer never issues update/delete on ledger tables;
  (2) DB `REVOKE UPDATE, DELETE` on the ledger role + `BEFORE UPDATE/DELETE` trigger raising an exception;
  (3) append-only partitioning by month (TimescaleDB/native) so old partitions can be set read-only.
- **Traceability:** every entry → `posting` → `correlation_id` → the originating order/signal event chain,
  giving a full "why does this balance exist" walk. `causation_id` gives the immediate parent.
- **Reconciliation jobs (scheduled):** (a) `SUM(signed_amount)=0` per posting; (b) trial balance
  `SUM(signed)=0` across the whole book; (c) `1210` cost == Σ open-lot cost basis; (d) `cash_balances`
  projection == live `SUM(entries)`; (e) `Assets = Liabilities + Equity`. Any mismatch pages (see monitoring
  design) and blocks EOD close.
- **Retention:** entries are permanent. Snapshots (trial balance, EOD) are stored for fast historical reads
  but are always reproducible from entries.

---

## 8. Open reconciliation with existing schema
The current `transactions` table is single-entry with `balance_after`. Migration path (see migration plan):
introduce `accounts`, `postings`, `ledger_entries`; backfill each historical `transaction` as a balanced
posting (cash leg + counter-leg inferred from `type`); keep `transactions` as a read view during transition,
then retire. No production data exists yet (greenfield), so backfill is trivial at implementation time.
