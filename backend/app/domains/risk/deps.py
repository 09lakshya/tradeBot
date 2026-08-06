"""FastAPI dependency injection providers for Risk Domain."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.risk.service import RiskService
from app.domains.trading.clock import Clock, SystemClock
from app.domains.trading.deps import get_clock


def get_risk_service(
    clock: Clock = Depends(get_clock),
) -> RiskService:
    """Provides a singleton-configured RiskService with the application Clock."""
    return RiskService(clock=clock)
