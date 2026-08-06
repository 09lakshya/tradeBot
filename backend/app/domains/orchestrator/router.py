"""FastAPI REST router for the Execution Orchestrator and Operational Dashboard."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.orchestrator.deps import get_event_bus, get_orchestrator_service
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.exceptions import OrchestratorException
from app.domains.orchestrator.schemas import (
    ContinuousMetricsResponse,
    ExecutionCycleRequest,
    ExecutionCycleResult,
    HealthMetricsResponse,
    InvariantReportResponse,
    PipelineStatusResponse,
    SessionStatusResponse,
)
from app.domains.orchestrator.service import ExecutionOrchestratorService

router = APIRouter(prefix="/orchestrator", tags=["execution-orchestrator"])


@router.post("/cycle/run", response_model=ExecutionCycleResult, status_code=status.HTTP_200_OK)
def run_execution_cycle(
    req: ExecutionCycleRequest,
    db: Session = Depends(get_db),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> ExecutionCycleResult:
    """Triggers an end-to-end execution cycle across all subsystems."""
    try:
        return service.execute_cycle(db=db, req=req)
    except OrchestratorException as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> PipelineStatusResponse:
    """Returns high-level pipeline status and cycle aggregates."""
    return service.get_pipeline_status()


@router.get("/session", response_model=SessionStatusResponse)
def get_session_status(
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> SessionStatusResponse:
    """Returns the current Indian market (NSE/BSE) trading session state and holidays."""
    return service.get_session_status()


@router.get("/health", response_model=HealthMetricsResponse)
def get_health_metrics(
    db: Session = Depends(get_db),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> HealthMetricsResponse:
    """Returns real-time health and latency metrics for all subsystems."""
    return service.get_health_metrics(db=db)


@router.get("/metrics/{portfolio_id}", response_model=ContinuousMetricsResponse)
def get_continuous_metrics(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> ContinuousMetricsResponse:
    """Returns live continuous financial performance metrics for a portfolio."""
    try:
        return service.get_continuous_metrics(db=db, portfolio_id=portfolio_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.post("/invariants/verify/{portfolio_id}", response_model=InvariantReportResponse)
def verify_invariants(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
) -> InvariantReportResponse:
    """Forces an on-demand reconciliation of financial and ledger invariants."""
    return service.verify_invariants(db=db, portfolio_id=portfolio_id)


@router.get("/cycles/{portfolio_id}")
def get_cycle_history(
    portfolio_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
):
    """Retrieves paginated history of past execution cycles."""
    records = service.get_cycle_history(db=db, portfolio_id=portfolio_id, limit=limit)
    return [
        {
            "id": str(r.id),
            "portfolio_id": str(r.portfolio_id),
            "timestamp": r.timestamp,
            "mode": r.mode,
            "duration_ms": r.duration_ms,
            "status": r.status,
            "signals_evaluated_count": r.signals_evaluated_count,
            "candidate_orders_count": r.candidate_orders_count,
            "orders_submitted_count": r.orders_submitted_count,
            "orders_filled_count": r.orders_filled_count,
            "stage_latencies": r.stage_latencies,
            "error_message": r.error_message,
        }
        for r in records
    ]


@router.get("/events")
def get_recent_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Retrieves recent immutable domain events emitted across the internal event bus."""
    events = event_bus.get_history(limit=limit)
    return [e.to_dict() for e in events]


@router.post("/scheduler/start")
def start_scheduler(
    interval_seconds: float = Query(default=60.0, gt=0),
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
):
    """Starts the background autonomous paper trading scheduler."""
    service.scheduler.set_interval(interval_seconds)
    return {"message": "Scheduler started", "interval_seconds": interval_seconds}


@router.post("/scheduler/stop")
def stop_scheduler(
    service: ExecutionOrchestratorService = Depends(get_orchestrator_service),
):
    """Stops the background autonomous paper trading scheduler."""
    service.scheduler.stop()
    return {"message": "Scheduler stopped"}
