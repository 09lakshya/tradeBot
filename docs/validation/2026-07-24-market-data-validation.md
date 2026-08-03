# Market Data Layer — Live Validation Report

Generated 2026-07-23T18:36:15.158565+00:00 · run `market02`

## Instrument discovery

- **Total discovered:** 13,611
- **Active / tradable:** 7,788
- **Inactive:** 5,823 (of which delisted 4,593)
- **By exchange:** {'BSE': 10754, 'NSE': 2857}
- **By asset class:** {'equity': 13140, 'etf': 332, 'index': 139}
- **With ISIN:** 11,280 · missing 2,331
- **Dual listings cross-mapped:** 2,440
- **Duplicate/ambiguity groups:** 0
- **Discovery time:** 7.36s

| Source | Exchange | Asset class | OK | Count | Seconds |
|---|---|---|---|---|---|
| `bse_equity` | BSE | equity | yes | 10,773 | 4.214 |
| `nse_equity` | NSE | equity | yes | 2,386 | 2.286 |
| `nse_etf` | NSE | etf | yes | 332 | 0.362 |
| `nse_index` | NSE | index | yes | 139 | 0.295 |

Calendar coverage: {'NSE': [2026], 'BSE': [2026]}

## Validation coverage

- **Instruments in queue:** 7,788
- **Timeframes:** 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo
- **Units attempted:** 1,125 of 70,092 (1.61%)
- **Remaining:** 68,967
- **Status breakdown:** {'no_data': 344, 'passed': 781}
- **Bars ingested:** 242,403
- **Bars quarantined:** 258
- **Missing intervals detected:** 89,500
- **Mean unit latency:** 1447.85 ms

### Units by timeframe

| Timeframe | Units |
|---|---|
| 15m | 125 |
| 1d | 125 |
| 1h | 125 |
| 1m | 125 |
| 1mo | 125 |
| 1w | 125 |
| 30m | 125 |
| 4h | 125 |
| 5m | 125 |

## Findings

- **By severity:** {'warning': 419, 'info': 164}

| Code | Count |
|---|---|
| `provider_error` | 344 |
| `session_grid_offset` | 90 |
| `quarantined_bars` | 74 |
| `all_zero_volume` | 56 |
| `synthetic_bar_outside_calendar_coverage` | 19 |

## Quarantine

| Reason | Bars |
|---|---|
| `calendar_mismatch` | 223 |
| `corrupted` | 9 |
| `invalid_ohlc` | 9 |
| `negative_price` | 56 |

## Failed units

Total failing findings: 0

