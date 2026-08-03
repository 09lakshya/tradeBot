"""FastAPI dependency injection providers for the Trading domain."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.trading.clock import Clock, SystemClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.service import TradingService

# Singleton instances for production FastAPI runtime
_SYSTEM_CLOCK = SystemClock()
_COST_ENGINE = CostEngine()


def get_clock() -> Clock:
    return _SYSTEM_CLOCK


def get_cost_engine() -> CostEngine:
    return _COST_ENGINE


def get_trading_service(
    db: Annotated[Session, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    cost_engine: Annotated[CostEngine, Depends(get_cost_engine)],
) -> TradingService:
    return TradingService(db=db, clock=clock, cost_engine=cost_engine)
