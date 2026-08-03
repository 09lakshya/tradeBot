# ADR 0005 — Corporate-action adjustment is provider-aware

**Status:** Accepted (2026-07-24). Found and fixed during live validation of the
Market Data Layer.

## Context

The Corporate Action engine back-adjusts historical prices so a series stays
continuous across splits and bonuses — without it, a 1:2 split reads as a 50%
overnight crash and every backtest on that series is wrong.

Live validation surfaced the mirror-image bug. Yahoo's `Close` — even with
`auto_adjust=False` — is **already split-adjusted**. Verified directly on
ACUTAAS around its 2025-04-25 1:2 split:

```
2025-04-24  close 1101.25
2025-04-25  close 1069.80   (ex-date, Stock Splits = 2.0)
2025-04-28  close 1109.30
```

The price is continuous across the ex-date, not halved. Yahoo reports the split
in its actions feed *and* folds it into the Close. Our pipeline was:

1. fetch Yahoo Close (already split-adjusted)
2. load the split from the actions feed
3. apply the split factor **again**

— halving every pre-split bar a second time. This is a silent data-leakage
defect: the series looks plausible, but every price before every historical split
is wrong by the split ratio (or its product, across multiple splits). It would
have poisoned every indicator and backtest built on the data, which is precisely
the failure mode the project treats as existential.

## Decision

Providers declare which corporate-action types they have already applied to the
bars they return, via `OHLCVResponse.pre_adjusted`. The service applies only the
actions **not** in that set:

```python
actions = [a for a in load_corporate_actions(instrument_id)
           if a.action_type not in response.pre_adjusted]
```

Yahoo declares `pre_adjusted = {split, bonus}` — the share-count events it folds
into Close. Dividends are *not* pre-applied (that is what Yahoo's `Adj Close`
adds), so they remain the engine's responsibility. A raw feed declares the empty
set and is adjusted in full, exactly as before.

The flag rides on the response, not the provider object, so a failover chain
behaves correctly: whichever provider actually served the bars stamps what it
pre-adjusted.

## Consequences

- (+) The stored series is continuous across splits regardless of which provider
  served it. Verified live: 10/10 real splits (ratios up to 1:10) are continuous
  across their ex-dates after the fix; before it they showed the full split-ratio
  discontinuity.
- (+) The contract is explicit and testable — a provider that lies about
  pre-adjustment fails an integration check rather than silently corrupting data.
- (−) Every new provider must correctly declare `pre_adjusted`. Getting it wrong
  in either direction (over- or under-declaring) breaks continuity, so it is
  covered by regression tests that assert the continuity property directly rather
  than trusting the flag.

## Validation method

The check does not compare adjustment *factors* against a provider convention we
do not control (the original attempt did, and mis-flagged correct output). It
asserts the property that actually matters: the ratio of consecutive stored
closes across a split ex-date is ~1 (continuous), never ~0.5 (unapplied) or ~2
(double-applied). Run via
`run_live_validation.py corporate-actions`.
