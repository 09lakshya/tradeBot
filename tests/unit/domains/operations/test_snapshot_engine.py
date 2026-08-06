"""Unit tests for Daily Portfolio Snapshot Engine."""
from __future__ import annotations

from pathlib import Path
from app.domains.operations.snapshot_engine import DailySnapshotEngine


def test_create_and_list_daily_snapshots(tmp_path: Path):
    engine = DailySnapshotEngine(snapshot_dir=tmp_path)
    snap1 = engine.create_snapshot(date="2026-08-01", portfolio_value=100000.0)
    snap2 = engine.create_snapshot(date="2026-08-02", portfolio_value=102000.0)

    assert snap1.date == "2026-08-01"
    assert snap2.portfolio_value == 102000.0

    retrieved = engine.get_snapshot("2026-08-01")
    assert retrieved is not None
    assert retrieved.portfolio_value == 100000.0

    all_snaps = engine.list_snapshots()
    assert len(all_snaps) == 2
    assert all_snaps[0].date == "2026-08-01"
    assert all_snaps[1].date == "2026-08-02"
