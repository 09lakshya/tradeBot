"""FastAPI REST router for the Execution Orchestrator and Operational Dashboard."""
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.market_data.models import Instrument
from app.domains.orchestrator.autotrader import AutoTrader, get_autotrader
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
from app.domains.trading.models import Order, OrderDecision

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
    autotrader: AutoTrader = Depends(get_autotrader),
):
    """Start the autonomous paper trading loop.

    This used to only call ``set_interval`` and report success without starting
    anything, so the caller was told the scheduler was running when no work was
    ever scheduled.
    """
    started = autotrader.start()
    return {
        "message": "Autotrader started" if started else "Autotrader already running",
        "started": started,
        "status": autotrader.status(),
    }


@router.post("/scheduler/stop")
async def stop_scheduler(
    autotrader: AutoTrader = Depends(get_autotrader),
):
    """Stop the autonomous paper trading loop."""
    await autotrader.stop()
    return {"message": "Autotrader stopped", "status": autotrader.status()}


@router.get("/autotrader/status")
def autotrader_status(autotrader: AutoTrader = Depends(get_autotrader)):
    """Live view of the autonomous loop: session gate, cycle counts, last result."""
    return autotrader.status()


@router.get("/autotrader/trades")
def autotrader_trades(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=500),
):
    """Recent trades with the strategies that caused them, ready to render.

    The orders endpoint returns instrument ids and leaves attribution inside a
    nested decision blob, so a UI would have to resolve symbols one by one. This
    returns the joined, flattened view a live feed actually needs.
    """
    rows = db.execute(
        select(Order, Instrument, OrderDecision)
        .join(Instrument, Instrument.id == Order.instrument_id)
        .outerjoin(OrderDecision, OrderDecision.order_id == Order.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    ).all()

    trades = []
    for order, instrument, decision in rows:
        raw = (decision.raw_signals if decision else None) or {}
        fills = list(order.fills or [])
        charges = sum((f.total_charges or Decimal("0")) for f in fills)
        trades.append(
            {
                "order_id": str(order.id),
                "symbol": instrument.trading_symbol,
                "name": instrument.name,
                "side": order.side.value if hasattr(order.side, "value") else str(order.side),
                "status": order.status.value
                if hasattr(order.status, "value")
                else str(order.status),
                "quantity": str(order.quantity),
                "filled_quantity": str(order.filled_quantity),
                "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
                "stop_price": str(order.stop_price) if order.stop_price else None,
                "notional": str(
                    (order.avg_fill_price or Decimal("0")) * (order.filled_quantity or Decimal("0"))
                ),
                "total_charges": str(charges),
                "strategies": list(raw.get("strategy_sources") or []),
                "confidence": str(decision.model_confidence) if decision else None,
                "risk_reward": str(decision.risk_reward_ratio)
                if decision and decision.risk_reward_ratio
                else None,
                "reason": decision.entry_reason if decision else None,
                "ranking_score": raw.get("ranking_score"),
                "sizing_method": raw.get("sizing_method"),
                "created_at": order.created_at.isoformat() if order.created_at else None,
            }
        )

    # How often each strategy contributed, so the UI can show what is driving it.
    usage: dict[str, int] = {}
    for t in trades:
        for sid in t["strategies"]:
            usage[sid] = usage.get(sid, 0) + 1

    return {
        "count": len(trades),
        "strategy_usage": dict(sorted(usage.items(), key=lambda kv: kv[1], reverse=True)),
        "trades": trades,
    }


@router.post("/autotrader/run-once")
def autotrader_run_once(
    force: bool = Query(default=False, description="Bypass the market-hours gate (testing)"),
    autotrader: AutoTrader = Depends(get_autotrader),
):
    """Run a single cycle now, without starting the loop."""
    return autotrader.run_cycle(force=force).as_dict()
