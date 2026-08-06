"""FastAPI REST router for Portfolio Construction & Signal Arbitration Engine."""
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.portfolio.deps import get_portfolio_service
from app.domains.portfolio.enums import AllocationPolicyType, ArbitrationMethod, RankingMethod, SizingMethod
from app.domains.portfolio.models import CandidateOrderRecord, PortfolioConstructionPlan
from app.domains.portfolio.schemas import (
    CandidateOrder,
    PortfolioConstructionConfig,
    PortfolioConstructionPlanResponse,
    PortfolioEngineMetricsResponse,
    PortfolioEvaluationRequest,
)
from app.domains.portfolio.service import PortfolioConstructionService

router = APIRouter(prefix="/portfolio-construction", tags=["portfolio-construction"])


@router.get("/status")
def get_portfolio_construction_status(
    service: Annotated[PortfolioConstructionService, Depends(get_portfolio_service)],
) -> dict[str, Any]:
    """Returns engine status and available configurations."""
    return {
        "status": "online",
        "domain": "portfolio_construction",
        "version": "1.0.0",
        "clock_time": service.clock.now().isoformat(),
        "available_policies": [p.value for p in AllocationPolicyType],
        "available_ranking_methods": [r.value for r in RankingMethod],
        "available_arbitration_methods": [a.value for a in ArbitrationMethod],
        "available_sizing_methods": [s.value for s in SizingMethod],
    }


@router.get("/metrics", response_model=PortfolioEngineMetricsResponse)
def get_portfolio_construction_metrics(
    service: Annotated[PortfolioConstructionService, Depends(get_portfolio_service)],
) -> PortfolioEngineMetricsResponse:
    """Returns aggregate optimization throughput and latency metrics."""
    return service.get_metrics()


@router.get("/policies")
def list_available_policies() -> dict[str, Any]:
    """Returns detailed descriptions of supported allocation, ranking, and sizing policies."""
    return {
        "allocation_policies": {
            AllocationPolicyType.equal_weight.value: "Equal capital distribution (1/K) across selected candidate assets",
            AllocationPolicyType.volatility_inverse.value: "Inverse rolling volatility weighting (1/sigma)",
            AllocationPolicyType.score_proportional.value: "Weighting proportional to multi-factor ranking score",
            AllocationPolicyType.risk_parity.value: "Equal Risk Contribution (ERC) under uncorrelated asset assumptions",
        },
        "ranking_methods": {
            RankingMethod.multi_factor_linear.value: "Linear combination of confidence, Sharpe, risk/reward, and freshness",
            RankingMethod.confidence_weighted.value: "Ranks purely by strategy confidence",
            RankingMethod.risk_reward_weighted.value: "Ranks by target risk/reward ratio",
            RankingMethod.sharpe_weighted.value: "Ranks by historical strategy Sharpe ratio",
        },
        "sizing_methods": {
            SizingMethod.fixed_fractional.value: "Target equity fraction divided by estimated price",
            SizingMethod.volatility_adjusted.value: "Fractional sizing adjusted by benchmark volatility ratio",
            SizingMethod.atr_risk_per_trade.value: "Position sized to risk fixed dollar amount to stop loss level",
            SizingMethod.half_kelly.value: "Damped Kelly Criterion (50% fractional Kelly)",
        },
    }


@router.post("/evaluate", response_model=PortfolioConstructionPlanResponse)
def evaluate_portfolio_construction(
    request: PortfolioEvaluationRequest,
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[PortfolioConstructionService, Depends(get_portfolio_service)],
) -> PortfolioConstructionPlanResponse:
    """Evaluates strategy signals against current portfolio state and generates immutable candidate orders."""
    try:
        snapshot = service.build_snapshot_from_db(
            db=db,
            portfolio_id=request.portfolio_id,
            current_prices=request.current_prices,
            volatilities=request.volatilities,
            sectors=request.sectors,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    plan = service.construct_portfolio(
        portfolio_snapshot=snapshot,
        signals=request.signals,
        config=request.config,
        current_prices=request.current_prices,
        instrument_sectors=request.sectors,
        db=db,
    )
    db.commit()
    return plan


@router.get("/plans")
def list_portfolio_plans(
    portfolio_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Annotated[Session, Depends(get_db)] = None,
) -> list[dict[str, Any]]:
    """Lists historical portfolio construction plans."""
    stmt = select(PortfolioConstructionPlan)
    if portfolio_id:
        stmt = stmt.where(PortfolioConstructionPlan.portfolio_id == portfolio_id)
    stmt = stmt.order_by(desc(PortfolioConstructionPlan.timestamp)).limit(limit)

    plans = list(db.scalars(stmt).all())
    return [
        {
            "id": p.id,
            "portfolio_id": p.portfolio_id,
            "timestamp": p.timestamp,
            "allocation_policy": p.allocation_policy,
            "sizing_method": p.sizing_method,
            "total_equity": p.total_equity,
            "cash_allocated": p.cash_allocated,
            "reserve_cash": p.reserve_cash,
            "candidate_order_count": len(p.candidate_orders),
            "summary_metrics": p.summary_metrics,
        }
        for p in plans
    ]


@router.get("/explain/{candidate_id}")
def explain_candidate_order(
    candidate_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Returns granular mathematical explainability ancestry trace for a candidate order."""
    rec = db.get(CandidateOrderRecord, candidate_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate order {candidate_id} not found",
        )

    return {
        "candidate_id": rec.id,
        "plan_id": rec.plan_id,
        "symbol": rec.symbol,
        "side": rec.side,
        "quantity": rec.quantity,
        "target_weight": rec.target_weight,
        "estimated_price": rec.estimated_price,
        "estimated_notional": rec.estimated_notional,
        "reasoning": rec.reasoning,
        "strategy_sources": rec.strategy_sources,
        "signal_sources": rec.signal_sources,
        "scoring_breakdown": rec.scoring_breakdown,
        "sizing_breakdown": rec.sizing_breakdown,
        "transaction_costs": rec.transaction_costs_json,
        "explainability_trace": rec.explainability_trace,
        "created_at": rec.created_at,
    }
