"""Strategy Health Monitoring & Degradation Detection Engine for Phase 10."""
from __future__ import annotations

import threading
from typing import Any

from app.domains.operations.models import StrategyHealthReport
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.strategy_health")


class StrategyHealthMonitor:
    """Continuously evaluates strategy performance drift and automatically flags degradation."""

    def __init__(self) -> None:
        self._reports: dict[str, StrategyHealthReport] = {}
        self._baselines: dict[str, dict[str, float]] = {
            "default": {
                "win_rate": 0.55,
                "profit_factor": 1.60,
                "sharpe_ratio": 1.50,
                "max_drawdown": 0.05,
            }
        }
        self._lock = threading.Lock()

    def set_strategy_baseline(
        self,
        strategy_id: str,
        win_rate: float = 0.55,
        profit_factor: float = 1.60,
        sharpe_ratio: float = 1.50,
        max_drawdown: float = 0.05,
    ) -> None:
        with self._lock:
            self._baselines[strategy_id] = {
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
            }

    def evaluate_strategy_health(
        self,
        strategy_id: str,
        current_win_rate: float,
        current_profit_factor: float,
        current_sharpe: float,
        current_drawdown: float,
        signal_freq: float = 4.2,
        trade_freq: float = 2.1,
        recent_pnl_30d: float = 1500.0,
        regime_perf: dict[str, float] | None = None,
    ) -> StrategyHealthReport:
        """Evaluates drift relative to baseline and flags strategy degradation."""
        baseline = self._baselines.get(strategy_id, self._baselines["default"])
        regime_perf = regime_perf or {"trending": 0.08, "ranging": -0.01, "volatile": 0.02}

        win_rate_drift = current_win_rate - baseline["win_rate"]
        pf_drift = current_profit_factor - baseline["profit_factor"]
        sharpe_drift = current_sharpe - baseline["sharpe_ratio"]
        dd_increase = current_drawdown - baseline["max_drawdown"]

        degradation_reasons: list[str] = []

        if win_rate_drift < -0.10:
            degradation_reasons.append(f"Win rate degraded by {abs(win_rate_drift):.1%}")

        if pf_drift < -0.30:
            degradation_reasons.append(f"Profit factor degraded by {abs(pf_drift):.2f}")

        if sharpe_drift < -0.50:
            degradation_reasons.append(f"Sharpe ratio degraded by {abs(sharpe_drift):.2f}")

        if dd_increase > 0.03:
            degradation_reasons.append(f"Drawdown expanded by {dd_increase:.1%}")

        is_degraded = len(degradation_reasons) > 0

        report = StrategyHealthReport(
            strategy_id=strategy_id,
            win_rate=current_win_rate,
            baseline_win_rate=baseline["win_rate"],
            win_rate_drift=round(win_rate_drift, 4),
            profit_factor=current_profit_factor,
            baseline_profit_factor=baseline["profit_factor"],
            profit_factor_drift=round(pf_drift, 4),
            sharpe_ratio=current_sharpe,
            baseline_sharpe=baseline["sharpe_ratio"],
            sharpe_drift=round(sharpe_drift, 4),
            current_drawdown=current_drawdown,
            max_drawdown_increase=round(dd_increase, 4),
            signal_frequency_per_day=signal_freq,
            trade_frequency_per_day=trade_freq,
            regime_performance=regime_perf,
            recent_pnl_30d=recent_pnl_30d,
            is_degraded=is_degraded,
            degradation_reasons=degradation_reasons,
        )

        with self._lock:
            self._reports[strategy_id] = report
            if is_degraded:
                logger.warning("strategy_degradation_detected", strategy_id=strategy_id, reasons=degradation_reasons)
            else:
                logger.info("strategy_health_nominal", strategy_id=strategy_id)

        return report

    def get_report(self, strategy_id: str) -> StrategyHealthReport | None:
        with self._lock:
            return self._reports.get(strategy_id)

    def list_reports(self) -> list[StrategyHealthReport]:
        with self._lock:
            return list(self._reports.values())
