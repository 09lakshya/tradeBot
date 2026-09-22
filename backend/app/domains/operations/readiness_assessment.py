"""Institutional Readiness Assessment Engine for Phase 10."""
from __future__ import annotations

from app.domains.operations.models import PillarScore, ReadinessAssessment, ReadinessStatus
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.readiness_assessment")


class ReadinessAssessmentEngine:
    """Quantitative scoring engine determining live deployment readiness across 10 evaluation pillars (0–100 scale)."""

    def evaluate_readiness(
        self,
        # Absence of evidence scores zero. These defaults used to be optimistic
        # constants (95.0, 88.0, ...) which made an account that had never traded
        # report 90.6/100 -- "READY FOR LIVE PILOT" -- to anyone calling this with
        # no arguments. A pillar is earned from measured performance or it is 0.
        profitability_score: float = 0.0,
        consistency_score: float = 0.0,
        drawdown_score: float = 0.0,
        risk_score: float = 0.0,
        trade_quality_score: float = 0.0,
        capital_utilization_score: float = 0.0,
        cost_efficiency_score: float = 0.0,
        strategy_stability_score: float = 0.0,
        regime_robustness_score: float = 0.0,
        benchmark_outperformance_score: float = 0.0,
    ) -> ReadinessAssessment:
        """Evaluates readiness against 10 institutional pillars."""
        pillar_definitions = [
            ("Profitability", profitability_score, 0.15, "Net return and P&L consistency"),
            ("Consistency", consistency_score, 0.10, "Daily win rate stability & low variance"),
            ("Drawdown", drawdown_score, 0.15, "Peak-to-trough equity preservation"),
            ("Risk", risk_score, 0.10, "VaR & Tail Risk compliance"),
            ("Trade Quality", trade_quality_score, 0.10, "Profit factor & payoff ratio"),
            ("Capital Utilization", capital_utilization_score, 0.05, "Optimal cash deployment efficiency"),
            ("Cost Efficiency", cost_efficiency_score, 0.10, "Slippage & commission Drag minimization"),
            ("Strategy Stability", strategy_stability_score, 0.10, "Absence of signal/win rate drift"),
            ("Market Regime Robustness", regime_robustness_score, 0.10, "Positive expectancy across trending, ranging & volatile regimes"),
            ("Benchmark Outperformance", benchmark_outperformance_score, 0.05, "Alpha generation over benchmark index"),
        ]

        pillars: list[PillarScore] = []
        total_weighted_score = 0.0

        for name, raw_score, weight, details in pillar_definitions:
            bounded_score = max(0.0, min(100.0, raw_score))
            w_score = bounded_score * weight
            total_weighted_score += w_score
            pillars.append(
                PillarScore(
                    name=name,
                    score=bounded_score,
                    weight=weight,
                    weighted_score=round(w_score, 2),
                    details=details,
                )
            )

        overall_score = round(total_weighted_score, 1)

        if overall_score >= 85.0:
            status = ReadinessStatus.ready_for_live_pilot
        elif overall_score >= 60.0:
            status = ReadinessStatus.needs_continuous_paper_trading
        else:
            status = ReadinessStatus.not_ready

        recommendations: list[str] = []
        if overall_score >= 85.0:
            recommendations.append("System demonstrates institutional stability. Proceed to Live Pilot with capped capital allocation.")
            recommendations.append("Maintain strict circuit breakers and real-time execution telemetry during initial deployment.")
        else:
            recommendations.append("Extend paper trading duration to collect additional market regime data.")
            recommendations.append("Optimize cost profiles and slippage models to improve net capital efficiency.")

        passed_count = sum(1 for p in pillars if p.score >= 80.0)

        assessment = ReadinessAssessment(
            overall_score=overall_score,
            status=status,
            pillars=pillars,
            passed_criteria_count=passed_count,
            total_criteria_count=len(pillars),
            recommendations=recommendations,
        )

        logger.info("readiness_assessment_evaluated", overall_score=overall_score, status=status.value)
        return assessment
