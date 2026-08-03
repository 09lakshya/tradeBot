"""initial schema + TimescaleDB hypertables

Greenfield bootstrap: enables the TimescaleDB extension, creates every table from
the ORM metadata (so this migration cannot drift from the models), then promotes
the time-series tables (ohlcv, equity_snapshots) to hypertables.

Subsequent schema changes MUST use ``alembic revision --autogenerate`` — this
create_all bootstrap is only appropriate for the very first migration.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-23
"""
from collections.abc import Sequence

from alembic import op
from app.models import Base  # registers all tables on Base.metadata

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that become TimescaleDB hypertables: (table, time column).
HYPERTABLES = [("ohlcv", "ts"), ("equity_snapshots", "ts")]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    Base.metadata.create_all(bind=bind)
    for table, time_col in HYPERTABLES:
        op.execute(
            f"SELECT create_hypertable('{table}', '{time_col}', "
            f"if_not_exists => TRUE, migrate_data => TRUE)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
