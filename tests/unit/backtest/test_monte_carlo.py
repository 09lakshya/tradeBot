"""Unit tests for Monte Carlo Robustness Simulator."""
import pytest

from app.domains.backtest.monte_carlo import MonteCarloSimulator
from app.domains.backtest.schemas import MonteCarloConfig


def test_monte_carlo_resampling_determinism():
    trades = [1200.0, -800.0, 1500.0, -600.0, 2000.0, -1100.0, 500.0, -400.0, 1800.0, -900.0] * 2

    config1 = MonteCarloConfig(
        iterations=500,
        random_seed=42,
        resample_method="block_bootstrap",
        block_size=4,
    )

    config2 = MonteCarloConfig(
        iterations=500,
        random_seed=42,
        resample_method="block_bootstrap",
        block_size=4,
    )

    res1 = MonteCarloSimulator.simulate(trades, initial_capital=100000.0, config=config1)
    res2 = MonteCarloSimulator.simulate(trades, initial_capital=100000.0, config=config2)

    assert res1.terminal_equity_quantiles == res2.terminal_equity_quantiles
    assert res1.max_drawdown_quantiles == res2.max_drawdown_quantiles
    assert res1.probability_of_ruin == res2.probability_of_ruin
    assert res1.var_95 == res2.var_95
    assert res1.cvar_95 == res2.cvar_95

    te = res1.terminal_equity_quantiles
    assert te["p5"] <= te["p25"] <= te["p50"] <= te["p75"] <= te["p95"]
