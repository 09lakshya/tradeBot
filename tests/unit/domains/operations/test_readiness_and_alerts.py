"""Unit tests for Readiness Assessment, Alerts & Historical Comparison."""
from __future__ import annotations

from pathlib import Path
from app.domains.operations.alert_center import OperationalAlertCenter
from app.domains.operations.historical_comparison import HistoricalComparisonEngine
from app.domains.operations.models import AlertSeverity, ReadinessStatus
from app.domains.operations.readiness_assessment import ReadinessAssessmentEngine


def test_readiness_assessment_scoring():
    engine = ReadinessAssessmentEngine()

    # Nominal high readiness. Every pillar is stated: unmeasured pillars now score
    # 0, so a partial call can no longer reach "ready" on optimistic defaults.
    res_high = engine.evaluate_readiness(
        profitability_score=95.0,
        consistency_score=90.0,
        drawdown_score=92.0,
        risk_score=90.0,
        trade_quality_score=88.0,
        capital_utilization_score=94.0,
        cost_efficiency_score=89.0,
        strategy_stability_score=93.0,
        regime_robustness_score=87.0,
        benchmark_outperformance_score=91.0,
    )
    assert res_high.overall_score >= 85.0
    assert res_high.status == ReadinessStatus.ready_for_live_pilot
    assert len(res_high.pillars) == 10

    # Low readiness
    res_low = engine.evaluate_readiness(
        profitability_score=40.0,
        consistency_score=50.0,
        drawdown_score=45.0,
        risk_score=50.0,
        trade_quality_score=40.0,
        capital_utilization_score=50.0,
        cost_efficiency_score=45.0,
        strategy_stability_score=40.0,
        regime_robustness_score=50.0,
        benchmark_outperformance_score=40.0,
    )
    assert res_low.overall_score < 60.0
    assert res_low.status == ReadinessStatus.not_ready


def test_readiness_defaults_to_zero_without_evidence():
    """No measured pillars means no readiness: an account that has never traded
    must not advertise itself as ready for a live pilot."""
    res = ReadinessAssessmentEngine().evaluate_readiness()
    assert res.overall_score == 0.0
    assert res.status == ReadinessStatus.not_ready


def test_operational_alert_center(tmp_path: Path):
    alert_center = OperationalAlertCenter(alert_dir=tmp_path)
    alert = alert_center.raise_alert(
        alert_type="strategy_degradation",
        title="Win Rate Dropped",
        message="Trend strategy win rate dropped below threshold",
        severity=AlertSeverity.warning,
    )
    assert alert.resolved is False

    resolved = alert_center.resolve_alert(alert.alert_id)
    assert resolved.resolved is True


def test_historical_comparison():
    engine = HistoricalComparisonEngine()
    result = engine.compare_periods(
        comparison_type="day_v_day",
        baseline_label="Yesterday",
        target_label="Today",
    )
    assert result.comparison_type == "day_v_day"
    assert "net_pnl" in result.metrics_comparison
    assert "Today" in result.summary_insight
