# Event Schemas — Technical Design

**Status:** Approved design (implements Event Metadata + Replay mandates, 2026-08-02) · **Phase:** Design-only
**Becomes:** part of ADR 0008 (event sourcing) · **Depends on:** `oms-paper-trading-core.md` §11, `ledger-architecture.md`.

> Scope guard: schemas and contracts only. No code, no serialization library chosen-by-fiat yet
> (Pydantic v2 models are the intended runtime representation, JSON the wire/storage form).

---

## 1. Envelope (every event, without exception)

All events share an immutable envelope. The payload varies per type; the envelope never does.

```jsonc
{
  "event_id":       "uuid",        // globally unique, stable, idempotency anchor
  "event_type":     "order.accepted",
  "event_version":  1,             // schema version of THIS event type (bump on breaking change)
  "aggregate_type": "order",       // order | position | portfolio | ledger | corporate_action | risk | strategy
  "aggregate_id":   "uuid",        // the entity this event mutates
  "sequence":       42,            // per-aggregate monotonic; optimistic-concurrency + replay ordering
  "occurred_at":    "2026-08-02T09:15:04.123456Z", // business time, Clock-sourced, UTC
  "recorded_at":    "2026-08-02T09:15:04.130000Z", // wall-clock persist time, UTC
  "correlation_id": "uuid",        // one logical flow: signal → order → fills → postings
  "causation_id":   "uuid",        // event_id of the direct cause (null for flow roots)
  "producer":       "oms.order_service",
  "schema_ref":     "events/order.accepted/v1",
  "payload":        { /* type-specific, below */ }
}
```

**Rules.**
- `event_id` is the dedup anchor; consumers must be idempotent on it.
- `sequence` is unique per `(aggregate_type, aggregate_id)` and gap-free; it doubles as the optimistic-lock
  version. A writer asserting `expected_sequence = N` fails if another writer advanced it.
- `correlation_id` is minted at the flow root (usually `signal.generated` or an API `order.submit`) and copied
  onto every downstream event. `causation_id` is the parent event's `event_id`.
- Time is always Clock-sourced UTC (never `datetime.now()`), enabling deterministic replay/simulation.
- **Versioning:** additive changes keep `event_version`; breaking changes bump it and register an upcaster
  (`v1 → v2`) so replay of old events still works. Never mutate a stored event.

---

## 2. Storage & transport

- **System of record:** `order_events` (per-order lifecycle) + `ledger_entries`/`postings` (financial) +
  a general `event_store` table for aggregate events not already covered. All append-only.
- **Transport:** transactional outbox (`oms_outbox`) written in the same txn as the state change; a relay
  publishes to the in-process bus (and Redis pub/sub for the WS gateway). Redis down ⇒ events queue in the
  outbox and drain on recovery — no loss.
- **Replay:** folding `event_store` (ordered by aggregate then `sequence`) through pure reducers reconstructs
  every projection. This is the substrate for the full-state-recovery mandate.

---

## 3. Event catalogue

Notation: **P** = producer, **C** = consumers. All inherit the §1 envelope; only `payload` shown.

### 3.1 Strategy / signal domain
| Event | `event_type` | Payload | P → C |
|---|---|---|---|
| Signal generated | `signal.generated` | `{strategy_id, instrument_id, side, strength, target_qty?, limit_price?, rationale, features_ref}` | Strategy Engine → OMS, Research/Analytics |
| Signal suppressed | `signal.suppressed` | `{strategy_id, instrument_id, reason}` | Strategy → Analytics |

### 3.2 Order domain (aggregate = order)
| Event | `event_type` | Payload |
|---|---|---|
| Submitted | `order.submitted` | `{client_order_id, portfolio_id, instrument_id, side, order_type, quantity, limit_price?, stop_price?, trail?, time_in_force, idempotency_key}` |
| Created | `order.created` | `{...normalized order snapshot}` |
| Validated | `order.validated` | `{checks_passed: [...]}` |
| Rejected (validation) | `order.rejected` | `{stage: "validation", reason_code, detail}` |
| Risk checked | `risk.checked` | `{verdict: passed\|blocked, rules: [{rule, result, detail}]}` |
| Accepted | `order.accepted` | `{reserved_amount, reservation_id}` |
| Rejected (risk) | `order.rejected` | `{stage: "risk", rule, detail}` |
| Pending (resting) | `order.pending` | `{resting_price, tif}` |
| Partially filled | `order.partially_filled` | `{fill_id, fill_seq, qty, price, cum_qty, leaves_qty}` |
| Filled | `order.filled` | `{fill_id, fill_seq, qty, price, cum_qty, avg_fill_price}` |
| Cancelled | `order.cancelled` | `{reason, cancelled_qty}` |
| Expired | `order.expired` | `{reason: "tif", tif}` |
| Replace requested | `order.replace_requested` | `{changes:{qty?,limit_price?,stop_price?}}` (future) |

**Terminal immutability:** after `filled\|cancelled\|rejected\|expired`, no further mutating events are valid;
only audit/annotation events may reference the order (enforced by state machine + DB, OMS §12).

### 3.3 Execution / fill domain
| Event | `event_type` | Payload | P → C |
|---|---|---|---|
| Fill recorded | `fill.recorded` | `{order_id, fill_id, fill_seq, instrument_id, side, qty, price, liquidity_flag, is_price_improved, charges:{brokerage,stt,gst,exchange,sebi,stamp,dp}, slippage}` | Execution Engine → Position Mgr, Ledger, Portfolio |

### 3.4 Position domain (aggregate = position)
| Event | `event_type` | Payload |
|---|---|---|
| Lot opened | `position.lot_opened` | `{position_id, lot_id, instrument_id, direction, qty, cost_basis, source_fill_id}` |
| Lot reduced | `position.lot_reduced` | `{lot_id, qty_closed, realized_pnl, remaining_qty}` |
| Position updated | `position.updated` | `{position_id, net_qty, avg_price, exposure}` |
| Position closed | `position.closed` | `{position_id, total_realized_pnl}` |
| Position marked | `position.marked` | `{position_id, mark_price, unrealized_pnl, as_of}` |

### 3.5 Ledger domain (aggregate = ledger/portfolio)
| Event | `event_type` | Payload |
|---|---|---|
| Posting recorded | `cash.posting_recorded` | `{posting_id, event_type, entries:[{account, direction, amount, instrument_id?}], correlation_id}` |
| Reservation created | `cash.reservation_created` | `{reservation_id, order_id, amount}` |
| Reservation released | `cash.reservation_released` | `{reservation_id, order_id, released, reason}` |
| Reservation adjusted | `cash.reservation_adjusted` | `{reservation_id, delta, remaining}` (partial fills) |

### 3.6 Portfolio / metrics domain
| Event | `event_type` | Payload | P → C |
|---|---|---|---|
| Portfolio updated | `portfolio.updated` | `{portfolio_id, cash, positions_value, equity, buying_power}` | Portfolio Mgr → Metrics, WS gateway |
| Equity snapshot | `metrics.equity_snapshot` | `{portfolio_id, equity, ts}` (→ `equity_snapshots` hypertable) | Metrics |
| Metrics updated | `metrics.updated` | `{portfolio_id, realized_pnl, unrealized_pnl, returns, drawdown}` | Metrics → WS, Risk (drawdown limit) |

### 3.7 Corporate-action domain (aggregate = corporate_action)
| Event | `event_type` | Payload |
|---|---|---|
| Detected | `corp_action.detected` | `{instrument_id, action_type: split\|bonus\|dividend\|buyback, ratio?, amount?, ex_date, record_date}` |
| Applied to positions | `corp_action.applied` | `{instrument_id, action_type, adjustments:[{position_id, old_qty, new_qty, old_cost, new_cost}]}` |
| Cash posted | `corp_action.cash_posted` | `{posting_id, action_type, amount}` (dividends/buybacks) |

### 3.8 Risk domain (aggregate = risk/portfolio)
| Event | `event_type` | Payload |
|---|---|---|
| Rule evaluated | `risk.rule_evaluated` | `{order_id, rule, result, observed, threshold}` |
| Limit breached | `risk.limit_breached` | `{scope, limit, observed, threshold, action}` |
| Kill switch toggled | `risk.kill_switch` | `{state: armed\|tripped\|reset, scope, reason, actor}` |
| Circuit breaker | `risk.circuit_breaker` | `{scope, trigger, cooloff_until}` |

### 3.9 System / lifecycle
| Event | `event_type` | Payload |
|---|---|---|
| Clock tick (sim/replay) | `system.clock_tick` | `{as_of, mode: live\|replay\|sim}` |
| Session opened/closed | `system.session` | `{exchange, state: open\|closed, ts}` |
| Projection rebuilt | `system.projection_rebuilt` | `{projection, scope, from_seq, to_seq}` |

---

## 4. Producer / consumer matrix (summary)

| Producer | Emits | Primary consumers |
|---|---|---|
| Strategy Engine | `signal.*` | OMS, Research |
| OMS Order Service | `order.*` | Risk, Execution, Metrics, WS |
| Risk Engine | `risk.*` | OMS (gate), Monitoring, WS |
| Execution Engine | `fill.recorded`, `order.partially_filled\|filled` | Position Mgr, Ledger, Portfolio |
| Position Manager | `position.*` | Ledger (realized P&L), Portfolio, Metrics |
| Ledger | `cash.*` | Portfolio (buying power), Monitoring (reconciliation) |
| Portfolio Manager | `portfolio.updated` | Metrics, WS, Risk (drawdown) |
| Metrics | `metrics.*` | WS, Risk, Dashboard |
| Corporate-action engine | `corp_action.*` | Position Mgr, Ledger, Market Data |
| Clock/Scheduler | `system.*` | all (replay/sim), Monitoring |

---

## 5. Schema governance
- Each event type has a directory `events/<type>/vN.json` (JSON Schema) + a Pydantic model at implementation.
- **Compatibility policy:** consumers ignore unknown fields (forward-compat); producers never remove/repurpose
  fields within a version. Breaking change ⇒ new `event_version` + upcaster registered in a central
  `EVENT_UPCASTERS` map, exercised by a replay regression test over stored fixtures.
- **Contract tests:** every producer has a test asserting emitted events validate against the current schema;
  every consumer has a test asserting it tolerates the min supported version. This prevents silent drift.
