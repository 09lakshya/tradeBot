"""Unit tests for Performance Metrics Calculator."""
import pytest
from app.domains.metrics.calculator import PerformanceMetricsCalculator


def test_performance_metrics_calculator():
    equity = [100000.0, 110000.0, 105000.0, 120000.0, 125000.0]
    trades = [10000.0, -5000.0, 15000.0, 5000.0]
    benchmark = [100.0, 102.0, 101.0, 105.0, 106.0]

    report = PerformanceMetricsCalculator.calculate(
        equity_series=equity,
        trade_pnls=trades,
        benchmark_series=benchmark,
    )

    assert report.total_return_pct == 25.0
    assert report.cagr_pct > 0.0
    assert report.sharpe_ratio > 0.0
    assert abs(report.max_drawdown_pct - 4.545) < 0.1
    assert report.total_trades == 4
    assert report.winning_trades == 3
    assert report.losing_trades == 1
    assert report.win_rate_pct == 75.0
    assert report.profit_factor == 6.0
    assert report.benchmark_return_pct == 6.0
    assert report.beta is not None
    assert report.alpha is not None
    assert 0.0 <= report.probabilistic_sharpe_ratio <= 1.0
    assert 0.0 <= report.deflated_sharpe_ratio <= 1.0
    assert 0.0 <= report.probability_of_backtest_overfitting <= 1.0
