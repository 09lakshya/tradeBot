"""Production-stack validation runner: PostgreSQL + TimescaleDB + Redis.

One command that stands the Market Data Layer up against the *production* storage
stack and proves the exit criteria, instead of relying on SQLite. It:

  1. connects to Postgres and confirms the TimescaleDB extension,
  2. applies the Alembic migration (`upgrade head`) and asserts hypertables,
  3. runs the Postgres-marked integration suite (`pytest -m postgres`),
  4. checks Redis connectivity and a cache round-trip,
  5. probes the FastAPI `/health/ready` readiness endpoint,
  6. writes a Markdown report to validation_artifacts/.

Nothing here is Windows- or Docker-specific: point it at any reachable stack.

Usage (from the repo root)::

    # The DB the app/migration use (env.py + config.py read these):
    export POSTGRES_USER=tradebot POSTGRES_PASSWORD=... POSTGRES_DB=tradebot_test
    export POSTGRES_HOST=localhost POSTGRES_PORT=5432
    export REDIS_HOST=localhost REDIS_PORT=6379
    # The integration tests read TEST_DATABASE_URL; keep it pointed at the SAME db:
    export TEST_DATABASE_URL=postgresql+psycopg://tradebot:...@localhost:5432/tradebot_test

    python backend/scripts/run_pg_validation.py

Exit code is non-zero if any mandatory check fails, so CI can gate on it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "validation_artifacts"
HYPERTABLES = ["ohlcv", "equity_snapshots"]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        return ok

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)


def _db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.database_url
    return url


def check_postgres(report: Report) -> None:
    print("\n== PostgreSQL / TimescaleDB ==")
    from sqlalchemy import create_engine, text
    engine = create_engine(_db_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            report.add("postgres.connect", True, _db_url().split("@")[-1])
            ver = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
            ).scalar()
            report.add("timescaledb.extension", ver is not None, f"v{ver}" if ver else "missing")
    except Exception as exc:  # noqa: BLE001
        report.add("postgres.connect", False, str(exc))
    finally:
        engine.dispose()


def check_migration(report: Report) -> None:
    print("\n== Alembic migration + hypertables ==")
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from alembic import command

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    try:
        command.upgrade(cfg, "head")
        report.add("alembic.upgrade_head", True)
    except Exception as exc:  # noqa: BLE001
        report.add("alembic.upgrade_head", False, str(exc))
        return

    engine = create_engine(_db_url(), future=True)
    try:
        with engine.connect() as conn:
            for table in HYPERTABLES:
                n = conn.execute(
                    text("SELECT count(*) FROM timescaledb_information.hypertables "
                         "WHERE hypertable_name=:t"),
                    {"t": table},
                ).scalar()
                report.add(f"hypertable.{table}", n == 1, "present" if n == 1 else "missing")
    finally:
        engine.dispose()


def check_integration_tests(report: Report) -> None:
    print("\n== Postgres integration suite (pytest -m postgres) ==")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "postgres", "-q",
         "tests/integration/test_market_data_pipeline.py",
         "tests/integration/test_pg_infrastructure.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    tail = (result.stdout + result.stderr).strip().splitlines()[-1:] or [""]
    report.add("pytest.-m postgres", result.returncode == 0, tail[0])
    if result.returncode != 0:
        print(result.stdout[-3000:])


def check_redis(report: Report) -> None:
    print("\n== Redis ==")
    from app.core.redis import get_redis
    client = get_redis()
    if client is None:
        report.add("redis.connect", False, "unreachable")
        return
    try:
        client.setex("md:validation:probe", 10, "ok")
        value = client.get("md:validation:probe")
        report.add("redis.roundtrip", value == "ok", f"got {value!r}")
    except Exception as exc:  # noqa: BLE001
        report.add("redis.roundtrip", False, str(exc))


def check_readiness_endpoint(report: Report) -> None:
    print("\n== FastAPI /health/ready ==")
    try:
        from fastapi.testclient import TestClient

        from app.main import create_app
        resp = TestClient(create_app()).get("/health/ready")
        body = resp.json()
        report.add("health.ready", resp.status_code == 200,
                   f"status={body.get('status')} db={body['checks']['database']['ok']}")
    except Exception as exc:  # noqa: BLE001
        report.add("health.ready", False, str(exc))


def write_report(report: Report) -> Path:
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = ARTIFACTS / f"pg_validation_{stamp}.md"
    lines = [
        "# PostgreSQL / TimescaleDB / Redis Validation Report",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Target: `{_db_url().split('@')[-1]}`",
        f"- Overall: **{'PASS' if report.passed else 'FAIL'}**",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for c in report.checks:
        lines.append(f"| {c.name} | {'✅ PASS' if c.ok else '❌ FAIL'} | {c.detail} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    print("Production-stack validation: PostgreSQL + TimescaleDB + Redis\n")
    report = Report()
    check_postgres(report)
    check_migration(report)
    check_integration_tests(report)
    check_redis(report)
    check_readiness_endpoint(report)
    path = write_report(report)
    print(f"\nReport written: {path}")
    print(f"\nOVERALL: {'PASS ✅' if report.passed else 'FAIL ❌'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
