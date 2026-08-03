"""Central import of all ORM models.

Importing this module registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``create_all`` rely on. Import it — never rely on
implicit discovery.
"""
from app.core.db import Base  # noqa: F401
from app.domains.backtest import models as backtest  # noqa: F401
from app.domains.market_data import models as market_data  # noqa: F401
from app.domains.metrics import models as metrics  # noqa: F401
from app.domains.platform import models as platform  # noqa: F401
from app.domains.risk import models as risk  # noqa: F401
from app.domains.trading import models as trading  # noqa: F401

__all__ = ["Base", "backtest", "market_data", "metrics", "platform", "risk", "trading"]
