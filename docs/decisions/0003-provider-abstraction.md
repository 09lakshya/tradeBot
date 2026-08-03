# ADR 0003 — Market data provider abstraction with failover

**Status:** Accepted (2026-07-23). Amended by
[ADR 0004](0004-instrument-discovery.md), which moves instrument-universe
discovery out of this interface and into dedicated sources.

## Context

Indian (NSE/BSE) market data coverage is uneven: Yahoo Finance works but is
unofficial, delayed, and has no instrument-universe endpoint; Alpha Vantage,
Twelve Data, and Finnhub have thin or paid Indian coverage. Binding the platform
to any single source is an existential risk for a system whose every downstream
component (strategies, backtester, risk) consumes this data.

## Decision

All sources implement one `MarketDataProvider` interface (Strategy Pattern) with
four methods: `fetch_instruments`, `fetch_ohlcv`, `fetch_corporate_actions`,
`health_check`. A `ProviderRouter` composes an ordered chain and transparently
applies token-bucket rate limiting, retry with exponential backoff + jitter,
metrics, and failover. Provider selection is configuration
(`MARKET_DATA_PROVIDER`, `MARKET_DATA_FALLBACKS`) resolved in one place
(`deps.py`); no other module knows which provider answered.

Providers are **pure adapters** returning normalized DTOs. The `MarketDataService`
is the sole writer of market data.

## Consequences

- (+) Yahoo is an initial adapter, not a dependency — replaceable without touching
  callers.
- (+) Transient failures are absorbed; hard failures fail over to the next source.
- (+) Adapters are testable offline; `MockProvider` injects timeouts, rate limits,
  and bad data to exercise resilience paths.
- (−) Normalization across heterogeneous providers is ongoing work; each new adapter
  must map into the DTOs faithfully.

## Notable design rules

- **Malformed data is never retried** (`ProviderDataError` fails fast); only
  timeouts, rate limits, and unavailability are transient.
- **Adapters refuse rather than guess.** Yahoo raises on `fetch_instruments` instead
  of fabricating a universe; the universe now comes from dedicated discovery
  sources (ADR 0004). `fetch_ohlcv` takes the instrument's **asset class**, because
  symbol conventions differ by class and a wrong mapping returns *another
  instrument's* prices rather than an error — Yahoo serves NSE indices as `^NSEI`,
  not `NIFTY 50.NS`, and several index names collide with tradable ETF tickers.
  Unmapped indices are refused.
- **Missing timeframes are derived, not refused.** Yahoo has no 4h interval, so it
  is aggregated from 1h via `resampling.py` rather than leaving a hole in the
  platform's timeframe surface. Derivation is session-anchored: a wall-clock 4h
  grid would split the 09:15–15:30 Indian session at a meaningless boundary.
- **Unimplemented adapters raise typed errors**, never silent wrong answers.
