"""create tables for domains missing from the model registry

``app/models.py`` imported eight of the eleven domains, and migration 0001 builds
the schema from ``Base.metadata`` -- so the orchestrator, operations and
portfolio-construction tables were never created. Nothing noticed until a live
execution cycle tried to persist an event and hit ``relation
"orchestrator_events" does not exist``; the tests use ``create_all`` against a
freshly imported metadata, which registers whatever the test itself imported.

``create_all`` with ``checkfirst`` adds only what is absent, so this is safe on a
database already carrying the 0001 tables.

Revision ID: 0002_missing_domains
Revises: 0001_initial
Create Date: 2026-09-21
"""
from collections.abc import Sequence

from alembic import op
from app.models import Base  # registers every domain's tables on Base.metadata

revision: str = "0002_missing_domains"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables this revision is responsible for. Drop order is taken from SQLAlchemy's
# dependency sort rather than written by hand: several of these carry foreign
# keys to each other (invariant checks -> execution cycles, arbitration and
# candidate records -> construction plans), and a hand-kept order silently rots
# the next time a relationship is added.
NEW_TABLES = frozenset({
    "orchestrator_events",
    "orchestrator_execution_cycles",
    "orchestrator_invariant_checks",
    "orchestrator_trading_sessions",
    "arbitration_audit_records",
    "candidate_order_records",
    "portfolio_construction_plans",
})


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    # sorted_tables is parents-first; reversed is children-first, which is the
    # only order in which these drops succeed.
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in NEW_TABLES:
            table.drop(bind=bind, checkfirst=True)
