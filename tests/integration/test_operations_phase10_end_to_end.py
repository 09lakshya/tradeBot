"""End-to-End Integration tests for Phase 10 REST API Endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_phase10_scheduler_api(client: TestClient):
    resp = client.get("/api/v1/operations/scheduler/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data
    assert "is_running" in data

    ctrl_resp = client.post("/api/v1/operations/scheduler/control", json={"action": "pause"})
    assert ctrl_resp.status_code == 200
    assert ctrl_resp.json()["mode"] == "paused"

    resume_resp = client.post("/api/v1/operations/scheduler/control", json={"action": "resume"})
    assert resume_resp.status_code == 200
    assert resume_resp.json()["mode"] == "autonomous"


def test_phase10_snapshots_api(client: TestClient):
    create_resp = client.post("/api/v1/operations/snapshots/create")
    assert create_resp.status_code == 200
    snap = create_resp.json()
    assert "snapshot_id" in snap
    assert "portfolio_value" in snap

    list_resp = client.get("/api/v1/operations/snapshots")
    assert list_resp.status_code == 200
    assert list_resp.json()["total_snapshots"] >= 1


def test_phase10_reports_api(client: TestClient):
    resp = client.post(
        "/api/v1/operations/reports/generate",
        json={
            "report_type": "daily",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "export_format": "html",
        },
    )
    assert resp.status_code == 200
    rep = resp.json()
    assert rep["format"] == "html"
    assert "<html>" in rep["rendered_content"]


def test_phase10_explainability_api(client: TestClient):
    payload = {
        "trade_id": "trd_api_1",
        "strategy_id": "trend_v1",
        "symbol": "MSFT",
        "side": "BUY",
        "signal_reason": {
            "indicators_involved": ["RSI"],
            "indicator_values": {"RSI": 28.0},
            "confidence_score": 0.90,
            "rationale": "Oversold signal",
        },
        "risk_reason": {
            "approved": True,
            "rules_evaluated": ["drawdown"],
            "rationale": "Limits compliant",
        },
        "portfolio_reason": {
            "accepted": True,
            "position_sizing_selected": 5000.0,
            "sizing_rationale": "Kelly sizing",
            "allocation_weight": 0.05,
        },
        "execution_reason": {
            "executed": True,
            "fill_price": 412.0,
            "slippage": 0.001,
            "commission": 2.0,
            "rationale": "Filled",
        },
    }

    rec_resp = client.post("/api/v1/operations/explainability/record", json=payload)
    assert rec_resp.status_code == 200
    exp = rec_resp.json()
    assert exp["trade_id"] == "trd_api_1"
    assert "Oversold signal" in exp["narrative"]

    get_resp = client.get("/api/v1/operations/explainability/trade/trd_api_1")
    assert get_resp.status_code == 200
    assert get_resp.json()["symbol"] == "MSFT"


def test_phase10_replay_and_dashboard_api(client: TestClient):
    create_sess = client.post("/api/v1/operations/replay/create?date=2026-08-04")
    assert create_sess.status_code == 200
    sess = create_sess.json()
    sess_id = sess["session_id"]

    act_resp = client.post(f"/api/v1/operations/replay/{sess_id}/action", json={"action": "step_forward"})
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "stepped_forward"

    dash_resp = client.get("/api/v1/operations/dashboard/replay?days=15")
    assert dash_resp.status_code == 200
    assert len(dash_resp.json()["equity_curve"]) == 15


def test_phase10_health_and_readiness_api(client: TestClient):
    health_resp = client.post("/api/v1/operations/health/evaluate?strategy_id=trend_v1")
    assert health_resp.status_code == 200
    assert "is_degraded" in health_resp.json()

    readiness_resp = client.post("/api/v1/operations/readiness/assess")
    assert readiness_resp.status_code == 200
    readiness = readiness_resp.json()
    assert readiness["overall_score"] >= 0.0
    assert readiness["status"] in [
        "READY FOR LIVE PILOT",
        "NEEDS CONTINUOUS PAPER TRADING",
        "NOT READY FOR LIVE DEPLOYMENT",
    ]


def test_phase10_experiments_notes_alerts_export_api(client: TestClient):
    # Experiment
    exp_req = {
        "name": "Parameter Comparison Test",
        "experiment_type": "parameter_comparison",
        "config": {
            "strategy_id": "trend_v1",
            "symbols": ["AAPL"],
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
            "parameters": {"lookback": 20},
        },
    }
    exp_resp = client.post("/api/v1/operations/experiments", json=exp_req)
    assert exp_resp.status_code == 200
    exp_id = exp_resp.json()["experiment_id"]

    run_resp = client.post(f"/api/v1/operations/experiments/{exp_id}/run")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "completed"

    # Note
    note_resp = client.post(
        "/api/v1/operations/notes",
        json={
            "entity_type": "experiment",
            "entity_id": exp_id,
            "author": "Analyst",
            "title": "Observation",
            "content_markdown": "Significant win rate boost.",
            "tags": ["experiment"],
        },
    )
    assert note_resp.status_code == 200

    # Alert
    alert_resp = client.post(
        "/api/v1/operations/alerts?alert_type=slippage&title=High%20Slippage&message=Slippage%20exceeded"
    )
    assert alert_resp.status_code == 200
    alert_id = alert_resp.json()["alert_id"]

    res_alert = client.post(f"/api/v1/operations/alerts/{alert_id}/resolve")
    assert res_alert.status_code == 200
    assert res_alert.json()["resolved"] is True

    # Export
    exp_data = client.post(
        "/api/v1/operations/export",
        json={"data_type": "analytics", "export_format": "json"},
    )
    assert exp_data.status_code == 200
    assert exp_data.json()["format"] == "json"
