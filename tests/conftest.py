"""Shared test fixtures.

Environment defaults are set before app config loads so tests never depend on a
developer's local .env. The DB fixture uses in-memory SQLite for fast, isolated
unit tests; Postgres-specific paths (upsert, hypertables) are covered by
integration tests marked ``postgres``.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("MARKET_DATA_PROVIDER", "mock")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.models import Base  # noqa: E402


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def mock_provider():  # noqa: ANN201
    from app.domains.market_data.providers.mock import MockProvider

    return MockProvider()


@pytest.fixture(autouse=True)
def isolate_operations_scratch(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """Keep the suite out of the app's live ``scratch/`` directory.

    The operations engines persist to paths like ``scratch/daily_snapshots``
    relative to the working directory, and several are module-level singletons
    created at import. Running the tests therefore wrote fixture data -- a
    snapshot claiming a 1,00,000 portfolio with 3,400 of realized P&L -- into
    the running application's state, where the dashboard then displayed it as
    real. Each test gets its own directory instead.
    """
    from pathlib import Path

    from app.domains.operations import (
        alert_center,
        autonomous_scheduler,
        deps,
        explainability_engine,
        research_notes,
        research_workspace,
        snapshot_engine,
    )

    root = tmp_path / "scratch"

    # Python binds default arguments at definition time, so rebinding the module
    # constant alone leaves ``Engine()`` still writing to the real directory --
    # the class's own __defaults__ have to be swapped too.
    def redirect(module, const, cls, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, const, path)
        defaults = cls.__init__.__defaults__ or ()
        patched = tuple(path if d is getattr(module, const, None) or isinstance(d, Path) else d
                        for d in defaults)
        monkeypatch.setattr(cls.__init__, "__defaults__", patched)

    for module, const, cls, name in (
        (snapshot_engine, "DEFAULT_SNAPSHOT_DIR", snapshot_engine.DailySnapshotEngine, "daily_snapshots"),
        (alert_center, "DEFAULT_ALERT_DIR", alert_center.OperationalAlertCenter, "operational_alerts"),
        (explainability_engine, "DEFAULT_EXPLANATION_DIR",
         explainability_engine.StrategyExplainabilityEngine, "trade_explanations"),
        (research_notes, "DEFAULT_NOTES_DIR", research_notes.ResearchNotesEngine, "research_notes"),
        (research_workspace, "DEFAULT_EXP_DIR", research_workspace.ResearchWorkspaceEngine, "experiments"),
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
        redirect(module, const, cls, root / name)

    redirect(
        autonomous_scheduler,
        "DEFAULT_STATE_FILE",
        autonomous_scheduler.AutonomousScheduler,
        root / "autonomous_scheduler_state.json",
    )

    # The singletons in deps.py already captured the old paths at import time.
    for singleton, attr, name in (
        (deps._snapshot_engine, "snapshot_dir", "daily_snapshots"),
        (deps._alert_center, "alert_dir", "operational_alerts"),
        (deps._explainability_engine, "storage_dir", "trade_explanations"),
        (deps._notes_engine, "notes_dir", "research_notes"),
        (deps._research_workspace, "exp_dir", "experiments"),
    ):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(singleton, attr, path)

    monkeypatch.setattr(
        deps._scheduler, "state_file", root / "autonomous_scheduler_state.json"
    )
    yield
