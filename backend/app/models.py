"""Central import of all ORM models.

Importing this module registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``create_all`` rely on. Import it — never rely on
implicit discovery.
"""
from app.core.db import Base  # noqa: F401
from app.domains.analytics import models as analytics  # noqa: F401
from app.domains.backtest import models as backtest  # noqa: F401
from app.domains.market_data import models as market_data  # noqa: F401
from app.domains.metrics import models as metrics  # noqa: F401
from app.domains.operations import models as operations  # noqa: F401
from app.domains.orchestrator import models as orchestrator  # noqa: F401
from app.domains.platform import models as platform  # noqa: F401
from app.domains.portfolio import models as portfolio  # noqa: F401
from app.domains.risk import models as risk  # noqa: F401
from app.domains.strategies import models as strategies  # noqa: F401
from app.domains.trading import models as trading  # noqa: F401

__all__ = [
    "Base",
    "analytics",
    "backtest",
    "market_data",
    "metrics",
    "operations",
    "orchestrator",
    "platform",
    "portfolio",
    "risk",
    "strategies",
    "trading",
]

