# ADR 0002 — PostgreSQL + TimescaleDB for time-series

**Status:** Accepted (2026-07-23)

## Context

OHLCV bars and equity-curve snapshots are high-volume time-series data. Plain Postgres
handles this but degrades on large range scans and lacks native compression.

## Decision

Use PostgreSQL as the single database, with the TimescaleDB extension for the two
time-series tables (`ohlcv`, `equity_snapshots`), promoted to hypertables in migration
`0001_initial`. Money columns use `NUMERIC`, never floating point.

## Consequences

- (+) Fast time-range queries, native compression/retention, one database to operate.
- (+) Falls back to plain Postgres semantics for all non-hypertable tables.
- (−) Adds an extension dependency; the Docker image is `timescale/timescaledb`.

## Alternatives considered

- **Plain Postgres:** viable, revisit if TimescaleDB ops burden isn't justified.
- **Dedicated TSDB (InfluxDB/Clickhouse):** rejected — a second datastore for early stage.
