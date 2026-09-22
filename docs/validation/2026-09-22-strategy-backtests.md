# Strategy backtests — first run

Generated 2026-09-22 · `backend/scripts/run_strategy_backtests.py` · raw results in
`strategy-backtests.json`

The first backtests ever run in this system. Until now no strategy had any
evidence behind it, contrary to ADR 0011, which requires strategies to be
developed against a validated backtester.

## Method

- **Universe**: 40 most liquid NSE names with ≥250 daily bars.
- **Split**: chronological. Fitted on 2024-09-23 → 2026-02-14, scored on
  2026-02-14 → 2026-09-21, which the strategy never saw.
- **Capital**: ₹10,00,000 per run, costs applied (brokerage, STT, GST, stamp duty).
- **Acceptance**: ≥5 trades, positive return, max drawdown ≤ 25% — all measured
  out-of-sample.

## Result: 9 of 22 kept

| Strategy | OOS return | Max DD | Trades |
|---|---:|---:|---:|
| rsi_momentum | +7.38% | 4.47% | 86 |
| stochastic_momentum | +3.64% | 4.16% | 194 |
| volume_breakout | +3.08% | 4.85% | 171 |
| vwap_reversion | +2.88% | 1.15% | 152 |
| bollinger_mean_reversion | +2.52% | 2.81% | 213 |
| obv_trend | +2.45% | 5.10% | 579 |
| zscore_reversion | +1.87% | 2.03% | 162 |
| donchian_breakout | +0.34% | 5.20% | 179 |
| relative_strength | +0.27% | 3.73% | 160 |

Rejected on negative out-of-sample return: opening_range_breakout (−3.57%),
macd_trend (−3.37%), atr_breakout (−3.13%), candlestick_patterns (−3.07%),
gap_trading (−3.01%), support_resistance (−2.00%), multi_factor_composite
(−1.58%), keltner_channel (−0.83%), momentum_ranking (−0.44%), adx_trend (−0.21%).

Rejected on producing no trades: sma_crossover, ema_crossover (0 trades — worth
investigating; a crossover strategy should fire over 18 months). composed_pipeline
failed to execute.

This list is set as `AUTOTRADER_STRATEGIES`. It matters because the portfolio
construction engine *blends* signals from every enabled strategy into one
decision per instrument — a losing strategy does not merely underperform, it
pollutes the consensus that sizes real positions.

## What these numbers do not tell you

1. **No benchmark comparison.** A positive return is not an edge. Over the same
   window a NIFTY tracker may well have returned more; none of these was measured
   against one. Treat "kept" as "not obviously broken", not "profitable".
2. **One split, not walk-forward.** A single chronological split is the weakest
   form of out-of-sample testing. `WalkForwardEngine` and `PurgedCrossValidation`
   exist and were not used here. Nine strategies surviving one window is partly
   luck; re-run across rolling windows before trusting the list.
3. **Fills are simulated** at the reference price with a slippage model. Real
   fills are worse, and the effect is largest for the higher-turnover strategies
   (obv_trend at 579 trades, gap_trading at 912).

## Two metrics in the report are wrong — do not use them

Found while reviewing this run; both are still broken.

**Sharpe and Sortino are meaningless here.** `PerformanceMetricsCalculator`
subtracts a daily risk-free rate (`risk_free_rate / 252`) from every observation
in the equity series, but the series is sampled per bar-event across all
instruments, so a 40-symbol run has roughly 40× more observations than trading
days. The risk-free drag is applied ~40× too often, which is why every strategy
scored between −6 and −22 regardless of whether it made or lost money, and why
zero-trade runs show −3149.70. Fix: resample the equity curve to one observation
per trading day before computing risk-adjusted metrics, or scale the risk-free
rate to the actual sampling interval.

**Win rate is always 0.0.** It counts trades with `realized_pnl > 0`, but buy
fills record `realized_pnl = 0` — only exits realise P&L. It is measuring the
proportion of fills that are profitable exits, which for a long-only strategy is
at most 50% by construction and reads as 0 when entries dominate.

The rankings above are ordered by return, not Sharpe, for this reason. The
keep/reject decision used only return, trade count and drawdown, all computed
directly off the equity curve.
