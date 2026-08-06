"""FastAPI dependency injection for Backtest domain."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.backtest.service import BacktestService
from app.domains.risk.service import RiskService


def get_backtest_service(db: Session = Depends(get_db)) -> BacktestService:
    risk_service = RiskService(db=db)
    return BacktestService(db=db, risk_service=risk_service)
