"""PostgreSQL / TimescaleDB schema-level validation.

Introspects a live database to prove the production storage contract the ORM and
migration promise: TimescaleDB hypertables, composite primary keys, expected
indexes and foreign keys, and a clean Alembic migration up/down cycle.

Skipped unless ``TEST_DATABASE_URL`` is set. Run with:

    TEST_DATABASE_URL=postgresql+psycopg://tradebot:...@localhost:5432/tradebot_test pytest -m postgres
"""
import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, inspect, text

from app.models import Base

DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set"),
]

HYPERTABLES = ["ohlcv", "equity_snapshots"]


@pytest.fixture
def migrated_engine() -> Iterator[Engine]:
    """Full schema built the migration's way: create_all + hypertable promotion."""
    engine = create_engine(DB_URL, future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in HYPERTABLES:
            conn.execute(
                text("SELECT create_hypertable(:t, 'ts', if_not_exists => TRUE, "
                     "migrate_data => TRUE)"),
                {"t": table},
            )
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_timescaledb_extension_is_installed(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        ).scalar()
    assert version is not None, "timescaledb extension must be enabled"


@pytest.mark.parametrize("table", HYPERTABLES)
def test_time_series_tables_are_hypertables(migrated_engine: Engine, table: str) -> None:
    with migrated_engine.connect() as conn:
        # hypertable_name is the modern (TS 2.x) view column; fall back for older.
        found = conn.execute(
            text(
                "SELECT count(*) FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = :t"
            ),
            {"t": table},
        ).scalar()
    assert found == 1, f"{table} must be a TimescaleDB hypertable"


def test_ohlcv_composite_primary_key(migrated_engine: Engine) -> None:
    pk = inspect(migrated_engine).get_pk_constraint("ohlcv")
    assert set(pk["constrained_columns"]) == {"instrument_id", "timeframe", "ts"}


def test_equity_snapshots_composite_primary_key(migrated_engine: Engine) -> None:
    pk = inspect(migrated_engine).get_pk_constraint("equity_snapshots")
    assert set(pk["constrained_columns"]) == {"portfolio_id", "ts"}


def test_hypertable_partition_column_is_in_primary_key(migrated_engine: Engine) -> None:
    # TimescaleDB requires the time column to be part of every unique index; the
    # composite PK is how we satisfy that. Guard against a future PK change that
    # would silently break create_hypertable.
    insp = inspect(migrated_engine)
    for table in HYPERTABLES:
        assert "ts" in insp.get_pk_constraint(table)["constrained_columns"]


def test_instrument_indexes_exist(migrated_engine: Engine) -> None:
    insp = inspect(migrated_engine)
    indexed = {
        col
        for index in insp.get_indexes("instruments")
        for col in index["column_names"]
    }
    # Lookups the resolver and discovery rely on must be index-backed.
    for col in ("isin", "trading_symbol", "exchange", "nse_symbol", "bse_symbol"):
        assert col in indexed, f"instruments.{col} should be indexed"


def test_ohlcv_foreign_key_targets_instruments(migrated_engine: Engine) -> None:
    fks = inspect(migrated_engine).get_foreign_keys("ohlcv")
    assert any(fk["referred_table"] == "instruments" for fk in fks)


def test_corporate_action_unique_constraint(migrated_engine: Engine) -> None:
    uniques = inspect(migrated_engine).get_unique_constraints("corporate_actions")
    cols = {frozenset(u["column_names"]) for u in uniques}
    assert frozenset({"instrument_id", "action_type", "ex_date"}) in cols


def test_alembic_migration_up_and_down(migrated_engine: Engine) -> None:
    """The initial migration must apply and roll back cleanly against Postgres.

    Runs the real Alembic pipeline against the test database (env.py reads the
    same settings the app does, so the runner points those at this instance),
    then asserts the hypertables exist after ``upgrade head``.
    """
    from alembic import command
    from alembic.config import Config

    # Start from an empty database so the migration owns the whole build.
    Base.metadata.drop_all(migrated_engine)
    with migrated_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    cfg = Config(os.path.join("backend", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join("backend", "alembic"))
    cfg.set_main_option("sqlalchemy.url", DB_URL)

    command.upgrade(cfg, "head")
    with migrated_engine.connect() as conn:
        for table in HYPERTABLES:
            n = conn.execute(
                text("SELECT count(*) FROM timescaledb_information.hypertables "
                     "WHERE hypertable_name = :t"),
                {"t": table},
            ).scalar()
            assert n == 1, f"{table} must be a hypertable after upgrade"
    command.downgrade(cfg, "base")
