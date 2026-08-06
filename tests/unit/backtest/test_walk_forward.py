"""Unit tests for Walk-Forward Window Generation and Stitching."""
from datetime import date
import pytest

from app.domains.backtest.enums import WindowType
from app.domains.backtest.schemas import WalkForwardConfig
from app.domains.backtest.walk_forward import WalkForwardEngine, WalkForwardSegmentResult, WalkForwardWindow


def test_walk_forward_window_generation():
    start = date(2023, 1, 1)
    end = date(2024, 1, 1)

    config = WalkForwardConfig(
        window_type=WindowType.rolling,
        train_period_days=180,
        test_period_days=60,
        step_days=60,
        purge_window_days=5,
        embargo_pct=0.01,
    )

    windows = WalkForwardEngine.generate_windows(start, end, config)
    assert len(windows) >= 2

    w0 = windows[0]
    assert w0.train_start == start
    assert w0.train_end == date(2023, 6, 30)
    assert w0.purge_start == date(2023, 6, 30)
    assert w0.purge_end == date(2023, 7, 5)
    assert w0.test_start == date(2023, 7, 5)
    assert w0.test_end == date(2023, 9, 3)

    w1 = windows[1]
    assert w1.train_start == date(2023, 3, 2)


def test_walk_forward_oos_aggregation():
    w0 = WalkForwardWindow(0, date(2023, 1, 1), date(2023, 6, 1), date(2023, 6, 1), date(2023, 9, 1))
    w1 = WalkForwardWindow(1, date(2023, 3, 1), date(2023, 9, 1), date(2023, 9, 1), date(2023, 12, 1))

    seg0 = WalkForwardSegmentResult(
        window=w0,
        is_metrics={"sharpe_ratio": 1.5},
        oos_metrics={"sharpe_ratio": 1.2},
        is_equity_curve=[{"ts": "2023-01-01", "equity": 100000.0}, {"ts": "2023-06-01", "equity": 110000.0}],
        oos_equity_curve=[{"ts": "2023-06-01", "equity": 100000.0}, {"ts": "2023-09-01", "equity": 105000.0}],
        wfe_ratio=0.8,
    )

    seg1 = WalkForwardSegmentResult(
        window=w1,
        is_metrics={"sharpe_ratio": 1.8},
        oos_metrics={"sharpe_ratio": 1.4},
        is_equity_curve=[{"ts": "2023-03-01", "equity": 100000.0}, {"ts": "2023-09-01", "equity": 115000.0}],
        oos_equity_curve=[{"ts": "2023-09-01", "equity": 100000.0}, {"ts": "2023-12-01", "equity": 108000.0}],
        wfe_ratio=0.77,
    )

    summary = WalkForwardEngine.aggregate_oos_results([seg0, seg1], initial_capital=100000.0)
    assert summary.total_windows == 2
    assert summary.mean_is_sharpe == 1.65
    assert summary.mean_oos_sharpe == 1.3
    assert len(summary.concatenated_oos_equity_curve) == 2
