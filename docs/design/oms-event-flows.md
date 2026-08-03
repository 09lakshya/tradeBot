# OMS Event Flows — Sequence Diagrams

**Status:** Approved design · **Phase:** Design-only · **Depends on:** `oms-paper-trading-core.md` §15,
`event-schemas.md`, `ledger-architecture.md`. Diagrams are Mermaid (render in the artifact/GitHub).

> These expand the OMS design's §15 with the approved double-entry ledger, event metadata, reservation model,
> corporate actions, and recovery. Every arrow that crosses a domain boundary is an event (`event-schemas.md`).

Participants (consistent across diagrams):
`API` · `OMS` (Order Service) · `RISK` (Risk Engine gate) · `EXEC` (Execution/Fill Engine) ·
`POS` (Position Mgr) · `LEDGER` (double-entry ledger) · `PORT` (Portfolio Mgr) · `OUTBOX` (transactional
outbox) · `BUS` (relay → Redis/WS + metrics) · `MD` (Market Data).

---

## 1. Market order (happy path)

```mermaid
sequenceDiagram
  autonumber
  participant API
  participant OMS
  participant RISK
  participant EXEC
  participant POS
  participant LEDGER
  participant PORT
  participant OUTBOX
  participant BUS
  API->>OMS: submit(client_order_id, idempotency_key)
  OMS->>OMS: dedup on idempotency_key (existing? return it)
  OMS->>OMS: create → validated  [order.created, order.validated]
  OMS->>RISK: check(order)
  RISK-->>OMS: risk.checked(PASSED, rules[])
  OMS->>LEDGER: reserve worst-case BP  [cash.reservation_created]
  LEDGER-->>OMS: reservation_id  (Dr 1120 / Cr 1110)
  OMS->>OMS: accepted  [order.accepted]
  OMS->>EXEC: execute(order, bar/mark from MD)
  EXEC->>EXEC: fill deterministically (seed=order_id,fill_seq)
  EXEC-->>OMS: fill.recorded(qty,price,charges,slippage)
  Note over OMS,PORT: single DB transaction begins
  OMS->>POS: apply fill  [position.lot_opened, position.updated]
  OMS->>LEDGER: post trade+charges (balanced)  [cash.posting_recorded]
  OMS->>LEDGER: release/settle reservation  [cash.reservation_released]
  OMS->>OMS: filled  [order.filled]
  OMS->>OUTBOX: write all events (same txn)
  Note over OMS,PORT: DB transaction commits
  OUTBOX->>BUS: relay dispatches
  BUS->>PORT: portfolio.updated
  BUS-->>API: WS push (order + portfolio)
```

Invariants: no `accepted` without `risk.checked=PASSED`; no fill applied without the whole state-change txn
committing atomically; reservation always released on terminal state.

---

## 2. Limit order (rests, then fills)

```mermaid
sequenceDiagram
  autonumber
  participant API
  participant OMS
  participant RISK
  participant LEDGER
  participant MD
  participant EXEC
  API->>OMS: submit(limit, price=P, TIF=DAY)
  OMS->>RISK: check → PASSED
  OMS->>LEDGER: reserve worst-case (limit price P)  [cash.reservation_created]
  OMS->>OMS: accepted → pending (resting)  [order.accepted, order.pending]
  loop each market update while resting
    MD-->>EXEC: bar/tick
    EXEC->>EXEC: marketable? (bar low<=P for buy)
    alt marketable
      EXEC-->>OMS: fill.recorded (price improvement if bar better than P)
      OMS->>LEDGER: post + release reservation
      OMS->>OMS: filled  [order.filled]
    else not marketable
      EXEC-->>OMS: no fill this bar
    end
  end
  alt session close reached, still resting
    OMS->>LEDGER: release reservation  [cash.reservation_released]
    OMS->>OMS: expired  [order.expired]
  end
```

---

## 3. Partial fill (with incremental reservation adjustment)

```mermaid
sequenceDiagram
  autonumber
  participant EXEC
  participant OMS
  participant POS
  participant LEDGER
  participant BUS
  EXEC-->>OMS: fill.recorded(fill_seq=1, qty=40 of 100, price)
  Note over OMS,LEDGER: txn 1
  OMS->>POS: apply partial  [position.lot_opened, position.updated]
  OMS->>LEDGER: post trade+charges for 40  [cash.posting_recorded]
  OMS->>LEDGER: adjust reservation (release hold on filled 40)  [cash.reservation_adjusted]
  OMS->>OMS: partially_filled (cum=40, leaves=60)  [order.partially_filled]
  BUS-->>BUS: portfolio.updated
  EXEC-->>OMS: fill.recorded(fill_seq=2, qty=60, price)
  Note over OMS,LEDGER: txn 2 (idempotent on (order_id,fill_seq))
  OMS->>POS: apply remaining  [position.updated]
  OMS->>LEDGER: post trade+charges for 60
  OMS->>LEDGER: release remaining reservation  [cash.reservation_released]
  OMS->>OMS: filled (cum=100, avg_fill_price)  [order.filled]
```

Guarantee: applying `(order_id, fill_seq)` twice is a no-op (unique constraint + ledger `dedup_key`), so a
retried relay never double-counts a partial.

---

## 4. Order cancellation

```mermaid
sequenceDiagram
  autonumber
  participant API
  participant OMS
  participant LEDGER
  participant BUS
  API->>OMS: cancel(order_id)
  OMS->>OMS: guard: is state cancellable? (created/validated/accepted/pending/partially_filled)
  alt cancellable
    OMS->>LEDGER: release remaining reservation  [cash.reservation_released(reason=cancel)]
    OMS->>OMS: cancelled (keeps any filled qty)  [order.cancelled]
    BUS-->>API: WS push (cancelled)
  else terminal already
    OMS-->>API: 409 conflict (immutable; append audit note only)
  end
```

Race: a cancel arriving concurrently with a fill is resolved by per-aggregate serialization on `sequence` —
whichever commits first wins; the loser re-reads state and either no-ops (already filled) or cancels the
remainder.

---

## 5. Portfolio update / equity snapshot (MTM cadence)

Reflects Decision 4: position MTM per price update; portfolio MTM every 5s; EOD snapshot at close.

```mermaid
sequenceDiagram
  autonumber
  participant MD
  participant POS
  participant PORT
  participant METRICS
  participant WS
  MD-->>POS: price update (instrument)
  POS->>POS: mark position  [position.marked, unrealized_pnl]
  Note over PORT: portfolio MTM timer (every 5s, Clock-driven)
  PORT->>POS: read marks
  PORT->>PORT: equity = cash(available) + Σ position_value  [portfolio.updated]
  PORT->>METRICS: metrics.updated (returns, drawdown)
  METRICS->>WS: push realtime
  Note over METRICS: at session close
  METRICS->>METRICS: metrics.equity_snapshot → equity_snapshots hypertable
```

Drawdown from `metrics.updated` feeds the Risk Engine's drawdown/daily-loss limits (see risk design).

---

## 6. Corporate-action handling

```mermaid
sequenceDiagram
  autonumber
  participant MD
  participant CA as CorpActionEngine
  participant POS
  participant LEDGER
  participant PORT
  MD-->>CA: corp_action.detected (split/bonus/dividend/buyback, ex_date)
  Note over CA: on ex_date (Clock), before session marks
  alt split / bonus (share-count change, no cash)
    CA->>POS: adjust lots (qty×ratio, cost/share ÷ratio)  [corp_action.applied]
    Note over LEDGER: no value entry (1210 cost unchanged); memo posting for audit
  else cash dividend
    CA->>LEDGER: post Dr 1110 / Cr 4200 (amount×qty on record date)  [corp_action.cash_posted]
  else buyback / special cash
    CA->>POS: reduce accepted lots (if tendered)  [corp_action.applied]
    CA->>LEDGER: post cash + realized P&L legs
  end
  CA->>PORT: recompute exposure/value  [portfolio.updated]
```

Consistency with ADR 0005: market-data prices are already split/bonus adjusted upstream; the OMS corporate
action only adjusts **held quantities/cost basis**, never re-applies price adjustments — avoiding the
double-adjustment class of bug.

---

## 7. Recovery after failure

Three failure classes, each with a deterministic recovery from the append-only log.

### 7.1 Crash between state change and event dispatch (outbox drains)
```mermaid
sequenceDiagram
  autonumber
  participant OMS
  participant DB
  participant OUTBOX
  participant RELAY
  participant BUS
  OMS->>DB: state change + outbox row (ONE txn) ✔ committed
  Note over OMS: process crashes before relay runs
  RELAY->>OUTBOX: on restart, scan published_at IS NULL
  OUTBOX-->>RELAY: unpublished events (ordered)
  RELAY->>BUS: dispatch, mark published_at
```
No event is lost because the outbox row committed atomically with the state change. Consumers are idempotent,
so re-dispatch of an already-seen `event_id` is a no-op.

### 7.2 Projection corruption / drift
```mermaid
sequenceDiagram
  autonumber
  participant OPS
  participant REBUILD as ProjectionRebuilder
  participant STORE as event_store/ledger_entries
  OPS->>REBUILD: rebuild(projection, scope)
  REBUILD->>STORE: read events ordered by aggregate,sequence
  REBUILD->>REBUILD: fold through pure reducers
  REBUILD-->>OPS: projection restored (bit-identical)  [system.projection_rebuilt]
```

### 7.3 Full-state reconstruction (event replay)
```mermaid
sequenceDiagram
  autonumber
  participant REPLAY as ReplayEngine
  participant STORE as event_store
  participant CLOCK as Clock(replay mode)
  REPLAY->>CLOCK: set mode=replay, as_of=start
  loop events in order
    STORE-->>REPLAY: next event
    REPLAY->>REPLAY: apply to aggregate (same handlers as online)
    REPLAY->>CLOCK: advance to event.occurred_at
  end
  REPLAY-->>REPLAY: OMS state == pre-crash state (orders, positions, ledger, portfolio)
```
Because handlers are pure and time comes from the Clock, replay is deterministic: same events ⇒ same state.
This underpins bug reproduction, AI-decision replay, and day-replay validation.

---

## 8. Cross-cutting guarantees illustrated above
| Guarantee | Where enforced in the flows |
|---|---|
| Risk gate mandatory | §1/§2: `accepted` only after `risk.checked=PASSED` |
| Atomic state+event | §1/§3/§7.1: single DB txn writes state change + outbox row |
| Exactly-once effect | idempotent consumers keyed on `event_id` / `(order_id,fill_seq)` / ledger `dedup_key` |
| Reservation lifecycle | §1–§4: created on accept, adjusted on partial, released on terminal |
| No double-adjustment | §6: OMS adjusts qty/cost only; prices pre-adjusted upstream (ADR 0005) |
| Deterministic replay | §7.3: pure handlers + Clock |
