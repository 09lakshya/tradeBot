"""Health endpoints and Celery scheduler configuration.

These need no database or broker: the readiness probe is exercised against an
unreachable stack (conftest points at a Postgres that isn't running), which is
exactly the 503 path an orchestrator relies on. The Postgres-connected readiness
path is covered by the ``postgres``-marked integration suite.
"""
from fastapi.testclient import TestClient

from app.main import create_app
from app.workers.celery_app import celery


def _client() -> TestClient:
    return TestClient(create_app())


def test_liveness_is_always_ok() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_reports_503_when_database_unreachable(monkeypatch) -> None:
    # Exercise the 503 path when database connectivity fails.
    import app.main
    monkeypatch.setattr(app.main, "_check_database", lambda: (False, "connection refused"))
    resp = _client().get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"]["ok"] is False


def test_readiness_body_shape_lists_every_dependency() -> None:
    body = _client().get("/health/ready").json()
    assert set(body["checks"]) == {"database", "redis"}
    for check in body["checks"].values():
        assert "ok" in check and "detail" in check


def test_beat_schedule_covers_universe_calendar_eod_and_health() -> None:
    tasks = {job["task"] for job in celery.conf.beat_schedule.values()}
    assert {
        "market_data.sync_universe",
        "market_data.sync_calendar",
        "market_data.sync_eod",
        "market_data.sync_corporate_actions",
        "market_data.provider_health_probe",
    }.issubset(tasks)


def test_celery_serialization_is_json_only() -> None:
    # Pickle would be a remote-code-execution surface on the broker.
    assert celery.conf.task_serializer == "json"
    assert celery.conf.accept_content == ["json"]


def test_celery_reliability_flags() -> None:
    # acks_late + prefetch=1 => a crashed worker's job is redelivered, not lost.
    assert celery.conf.task_acks_late is True
    assert celery.conf.worker_prefetch_multiplier == 1
