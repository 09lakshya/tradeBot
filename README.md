# Trade Bot — Autonomous AI Trading Platform

Production-grade, AI-powered algorithmic trading platform. **Phase 1: paper trading only** (no real-money execution). Indian markets (NSE/BSE) first, designed for multi-asset expansion.

> Objective priority (risk always overrides profit):
> 1. Preserve capital 2. Maximize risk-adjusted returns 3. Minimize drawdown
> 4. Minimize downside volatility 5. Never chase 6. Skip uncertain trades 7. Every trade explainable

## Architecture

Modular monolith: a single FastAPI app with clean domain boundaries (`backend/app/domains/*`),
async workers via Celery + Redis, PostgreSQL + TimescaleDB for time-series. See `docs/ARCHITECTURE.md`.

The **Risk Engine is a mandatory pre-trade gate** — no order reaches the OMS unless every safety rule passes.

## Quick start (local)

```bash
cp .env.example .env          # fill in secrets
docker compose up --build     # api :8000, frontend :3000, postgres :5432, redis :6379
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs · Frontend: http://localhost:3000

## Market data validation

The Market Data Layer is validated against the **live market**, not a fixture set.
Discovery pulls the full NSE/BSE universe from the exchanges themselves, and
validation walks instrument × timeframe in resumable batches.

```bash
python backend/scripts/run_live_validation.py discover                  # universe + calendar
python backend/scripts/run_live_validation.py validate --batch-size 400 # resumable; re-run to extend
python backend/scripts/run_live_validation.py providers                 # failover/retry/rate-limit
python backend/scripts/run_live_validation.py report                    # consolidated report
```

`validate` records every unit to a checkpoint ledger and skips what is already
done, so it can be interrupted at any point and re-run until coverage reaches
100% under whatever quota the provider allows. Artifacts land in
`validation_artifacts/`; the committed report is in `docs/validation/`.

## Layout

| Path | Purpose |
|------|---------|
| `backend/app/domains/` | Bounded contexts: market_data, trading, risk, strategies, backtest, metrics, research, platform |
| `backend/app/core/` | Config, DB, logging, security (cross-cutting) |
| `backend/app/workers/` | Celery app, scheduled + long-running tasks |
| `frontend/` | Next.js dashboard |
| `deploy/` | Cloud-VM provisioning + DB backups |
| `docs/decisions/` | Architecture Decision Records (ADRs) |

## Build status

Correctness-first sequencing: data → paper OMS → risk → strategies → backtester → dashboard → AI research (last).
See `docs/ARCHITECTURE.md` for the current phase.
