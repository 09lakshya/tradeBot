"""Integration test suite for Phase 11 One-Month Autonomous Paper Trading Validation."""
from __future__ import annotations

import pytest
from app.domains.operations.validation_engine import validation_engine
from app.domains.operations.operational_metrics import operational_metrics_collector
from app.domains.operations.drift_detector import drift_detector_engine


def test_accelerated_validation_run_completes_30_sessions():
    """Verify Mode A Accelerated validation executes 30 trading session iterations."""
    summary = validation_engine.run_accelerated_validation()
    assert summary.completed_sessions == 30
    assert summary.target_sessions == 30
    assert summary.pass_fail_status == "PASS"
    assert summary.overall_readiness_score >= 90.0
    assert "HUMAN APPROVAL REQUIRED" in summary.human_approval_status
    assert len(summary.daily_snapshots) == 30


def test_financial_and_consistency_verifications():
    """Verify all 7 consistency verifiers and financial metrics are populated."""
    summary = validation_engine.run_accelerated_validation()
    verifications = summary.consistency_verifications

    assert verifications["replay_consistency"] is True
    assert verifications["ledger_reconciliation"] is True
    assert verifications["position_consistency"] is True
    assert verifications["portfolio_consistency"] is True
    assert verifications["risk_consistency"] is True
    assert verifications["candidate_order_consistency"] is True
    assert verifications["explainability_consistency"] is True

    fin = summary.financial_metrics
    assert fin["sharpe_ratio"] > 0
    assert fin["sortino_ratio"] > 0
    assert fin["profit_factor"] > 1.0
    assert fin["win_rate"] > 0.50


def test_operational_telemetry_collection():
    """Verify infrastructure operational metrics telemetry."""
    metrics = operational_metrics_collector.collect_metrics()
    assert metrics.scheduler_uptime_seconds >= 0
    assert metrics.worker_uptime_seconds >= 0
    assert metrics.api_availability_pct > 99.0
    assert metrics.websocket_reconnect_count >= 0
    assert metrics.memory_utilization_pct > 0


def test_statistical_drift_detector():
    """Verify drift analysis produces valid z-score metric evaluations."""
    report = drift_detector_engine.analyze_drift()
    assert report.overall_drift_status in ["NOMINAL", "WARNING", "DRIFT_DETECTED"]
    assert len(report.drifts) >= 5
    for d in report.drifts:
        assert isinstance(d.z_score, float)
        assert isinstance(d.is_drifted, bool)
