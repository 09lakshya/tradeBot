"""FastAPI Dependencies for Portfolio Construction Engine."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.trading.clock import Clock, SystemClock


_portfolio_service_instance: PortfolioConstructionService | None = None


def get_portfolio_service() -> PortfolioConstructionService:
    """Provides PortfolioConstructionService singleton with system clock."""
    global _portfolio_service_instance
    if _portfolio_service_instance is None:
        _portfolio_service_instance = PortfolioConstructionService(clock=SystemClock())
    return _portfolio_service_instance
