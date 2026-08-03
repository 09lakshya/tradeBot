"""Smoke tests: app boots, health responds, and all ORM models register cleanly."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ping() -> None:
    resp = client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json()["message"] == "pong"


def test_all_models_register() -> None:
    from app.models import Base

    tables = set(Base.metadata.tables)
    # Money-path and core tables must all be present.
    expected = {
        "users", "audit_log", "strategy_versions",
        "instruments", "ohlcv", "corporate_actions",
        "portfolios", "orders", "order_decisions", "fills", "positions", "transactions",
        "risk_limits", "risk_events", "kill_switches",
        "equity_snapshots", "performance_metrics",
        "backtests", "backtest_results",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"
