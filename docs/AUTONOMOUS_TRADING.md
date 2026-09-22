# Autonomous paper trading — runbook

**Paper only.** There is no broker integration in this system and the OMS makes
no outbound exchange calls. Cash is a number in the local ledger; no real money
can be placed at risk by this loop.

## What runs

```
every 15 min, while NSE is in regular hours (09:15–15:30 IST, weekdays, non-holidays)

  watchlist (200 most liquid) ─▶ live quotes ─▶ 22 strategies over daily bars
        ─▶ portfolio construction (sizing, caps) ─▶ risk gate ─▶ OMS ─▶ simulated fills
```

The loop starts with the API and idles outside the session, so the stack only
has to be up before the open — it begins trading by itself at the bell.

| Piece | Where |
|---|---|
| Loop + market-hours gate | `backend/app/domains/orchestrator/autotrader.py` |
| Quotes + strategy signals | `backend/app/domains/orchestrator/live_market.py` |
| Universe / watchlist / history | `backend/scripts/bootstrap_live_universe.py` |
| Tradable watchlist | `config/trading_universe.json` |
| Settings | `AUTOTRADER_*` in `.env` |

## Start / stop

```powershell
powershell -ExecutionPolicy Bypass -File .\start_trading.ps1   # whole stack
```

```bash
curl http://127.0.0.1:8001/api/v1/orchestrator/autotrader/status       # what it is doing
curl -X POST http://127.0.0.1:8001/api/v1/orchestrator/scheduler/stop  # stand it down
curl -X POST http://127.0.0.1:8001/api/v1/orchestrator/scheduler/start # arm it again
curl -X POST "http://127.0.0.1:8001/api/v1/orchestrator/autotrader/run-once?force=true"  # one cycle now
```

To disarm permanently, set `AUTOTRADER_ENABLED=false` in `.env` and restart.

## Risk limits in force

Defaults from `PortfolioConstructionConfig`, applied every cycle:

| Limit | Value |
|---|---|
| Risk per trade | 1% of equity |
| Stop-loss | ATR × 2 |
| Max per instrument | 10% of equity |
| Max per sector | 25% |
| Max per strategy | 35% |
| Max open positions | 10 |
| Cash reserve | 5% |

The risk engine is a mandatory pre-trade gate: an order breaching a limit is
rejected before it reaches the OMS, and the rejection is recorded.

## Refreshing data

The watchlist and its history should be refreshed periodically — the liquidity
screen goes stale and strategies need recent bars:

```bash
python backend/scripts/bootstrap_live_universe.py discover          # all listed NSE equities
python backend/scripts/bootstrap_live_universe.py rank --top 500    # liquidity screen
python backend/scripts/bootstrap_live_universe.py history --period 2y
python backend/scripts/bootstrap_live_universe.py status
```

## Known limitations — read before trusting a number

1. **No strategy has been backtested.** Zero backtests have run in this system.
   Per ADR 0011 strategies are supposed to be developed against a validated
   backtester precisely so none is tuned on an unverified engine. The P&L this
   produces is not evidence that any strategy works.
2. **Signals come from daily bars, not live ticks.** Yahoo intraday for NSE is
   delayed roughly 15 minutes and there is no tick feed here, so intraday entries
   are approximate. `AUTOTRADER_SIGNAL_TTL_SECONDS` is 86400 to match the daily
   cadence; at the engine default of 3600 every daily-bar signal is discarded as
   stale before it can become an order.
3. **Fills are simulated.** A paper fill assumes you could transact at the
   reference price. That assumption is least wrong in liquid names, which is why
   the watchlist is a liquidity screen rather than all 2,595 listed equities.
4. **Account size caps what can be traded.** The 10% per-instrument limit means a
   ₹5,000 wallet can commit ₹500 to a name, so anything above ₹500 a share is
   unbuyable. Below roughly ₹2–5 lakh the position sizing has very little room.
5. **The process must stay up.** The loop lives in the API process. A reboot
   stops it; re-run `start_trading.ps1`.
