"""FastAPI REST router for Risk Engine endpoints."""
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.risk.deps import get_risk_service
from app.domains.risk.enums import ScopeType
from app.domains.risk.models import CircuitBreaker, KillSwitch, RiskEvent, RiskLimit
from app.domains.risk.schemas import (
    CircuitBreakerResponse,
    KillSwitchResetRequest,
    KillSwitchResponse,
    KillSwitchTripRequest,
    RiskEventResponse,
    RiskLimitResponse,
    RiskLimitUpdate,
    RiskStatusSummary,
)
from app.domains.risk.service import RiskService

router = APIRouter(prefix="/risk", tags=["Risk Engine"])


@router.get("/limits/{portfolio_id}", response_model=RiskLimitResponse)
def get_risk_limits(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    risk_service: RiskService = Depends(get_risk_service),
):
    """Retrieve active risk limits for a portfolio."""
    return risk_service.get_or_create_limits(db, portfolio_id)


@router.put("/limits/{portfolio_id}", response_model=RiskLimitResponse)
def update_risk_limits(
    portfolio_id: uuid.UUID,
    updates: RiskLimitUpdate,
    db: Session = Depends(get_db),
    risk_service: RiskService = Depends(get_risk_service),
):
    """Update risk limits for a portfolio."""
    updated = risk_service.update_limits(db, portfolio_id, updates)
    db.commit()
    return updated


@router.get("/status/{portfolio_id}", response_model=RiskStatusSummary)
def get_risk_status(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    risk_service: RiskService = Depends(get_risk_service),
):
    """Get real-time risk health summary for a portfolio."""
    return risk_service.get_risk_status(db, portfolio_id)


@router.post("/kill-switch/{portfolio_id}/trip", response_model=KillSwitchResponse)
def trip_portfolio_kill_switch(
    portfolio_id: uuid.UUID,
    req: KillSwitchTripRequest,
    db: Session = Depends(get_db),
    risk_service: RiskService = Depends(get_risk_service),
):
    """Trip emergency kill switch for a portfolio."""
    ks = risk_service.trip_kill_switch(
        db=db,
        scope=ScopeType.portfolio,
        scope_id=str(portfolio_id),
        reason=req.reason,
        activated_by=req.activated_by,
    )
    db.commit()
    return ks


@router.post("/kill-switch/{portfolio_id}/reset", response_model=KillSwitchResponse)
def reset_portfolio_kill_switch(
    portfolio_id: uuid.UUID,
    req: KillSwitchResetRequest,
    db: Session = Depends(get_db),
    risk_service: RiskService = Depends(get_risk_service),
):
    """Reset emergency kill switch for a portfolio (audited)."""
    ks = risk_service.reset_kill_switch(
        db=db,
        scope=ScopeType.portfolio,
        scope_id=str(portfolio_id),
        reset_reason=req.reset_reason,
        reset_by=req.reset_by,
    )
    if not ks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active kill switch not found for portfolio",
        )
    db.commit()
    return ks


@router.get("/events/{portfolio_id}", response_model=list[RiskEventResponse])
def get_risk_events(
    portfolio_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retrieve pre-trade risk evaluation audit events."""
    events = db.execute(
        select(RiskEvent)
        .where(RiskEvent.portfolio_id == portfolio_id)
        .order_by(desc(RiskEvent.created_at))
        .limit(limit)
    ).scalars().all()
    return events
