"""Platform domain: users, auth, audit log, strategy version registry."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import Timestamps, UUIDPk


class Role(str, enum.Enum):
    admin = "admin"
    trader = "trader"
    viewer = "viewer"


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.trader)
    is_active: Mapped[bool] = mapped_column(default=True)


class AuditLog(UUIDPk, Base):
    """Append-only record of every security/state-changing action."""
    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class StrategyStatus(str, enum.Enum):
    candidate = "candidate"      # generated, under evaluation
    production = "production"    # currently live-selected
    archived = "archived"        # superseded / rolled back


class StrategyVersion(UUIDPk, Timestamps, Base):
    """Immutable, versioned strategy config. Research promotes candidates → production.

    Never overwrite: a new config = a new row. Full history + rollback preserved.
    """
    __tablename__ = "strategy_versions"

    strategy_key: Mapped[str] = mapped_column(String(100), index=True)  # e.g. "ema_crossover"
    version: Mapped[int] = mapped_column(default=1)
    params: Mapped[dict] = mapped_column(JSON)                          # tuned hyperparameters
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus), default=StrategyStatus.candidate, index=True
    )
    # Validation metrics snapshot captured at promotion time.
    metrics: Mapped[dict | None] = mapped_column(JSON)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_versions.id"))
