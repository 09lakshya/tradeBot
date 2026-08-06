"""Unit tests for Strategy Health Monitoring Engine."""
from __future__ import annotations

from app.domains.operations.strategy_health import StrategyHealthMonitor


def test_strategy_health_evaluation_nominal_and_degraded():
    monitor = StrategyHealthMonitor()

    # Nominal strategy health
    rep1 = monitor.evaluate_strategy_health(
        strategy_id="strat_1",
        current_win_rate=0.55,
        current_profit_factor=1.60,
        current_sharpe=1.50,
        current_drawdown=0.02,
    )
    assert rep1.is_degraded is False
    assert len(rep1.degradation_reasons) == 0

    # Degraded strategy health
    rep2 = monitor.evaluate_strategy_health(
        strategy_id="strat_2",
        current_win_rate=0.40,  # baseline 0.55 -> drift -0.15
        current_profit_factor=1.10,  # baseline 1.60 -> drift -0.50
        current_sharpe=0.80,  # baseline 1.50 -> drift -0.70
        current_drawdown=0.09,  # baseline 0.05 -> increase +0.04
    )
    assert rep2.is_degraded is True
    assert len(rep2.degradation_reasons) >= 3
