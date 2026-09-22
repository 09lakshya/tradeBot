"""FastAPI REST Router for Platform Observability, Health, Tracing, Audit & Operations."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.domains.platform.audit import AuditRecord, AuditTrailService
from app.domains.platform.circuit_breaker import (
    CircuitBreakerSnapshot,
    global_circuit_breaker_registry,
)
from app.domains.platform.config import (
    PlatformRuntimeConfig,
    global_runtime_config_service,
)
from app.domains.platform.health import HealthReport, global_health_monitor
from app.domains.platform.logging import StructuredLogEntry, global_log_buffer
from app.domains.platform.profiler import (
    PerformanceSnapshot,
    global_performance_profiler,
)
from app.domains.platform.schemas import (
    CircuitBreakerResetResponse,
    ConfigUpdateRequest,
    PlatformStatusResponse,
    ShutdownTriggerResponse,
)
from app.domains.platform.shutdown import global_shutdown_coordinator
from app.domains.platform.tracing import (
    SpanStatus,
    TraceRecord,
    global_trace_collector,
)

router = APIRouter(prefix="/platform", tags=["platform-observability"])
audit_service = AuditTrailService()


@router.get("/health", response_model=HealthReport)
def get_health(db: Annotated[Session, Depends(get_db)]) -> HealthReport:
    """Detailed diagnostic health evaluation across all platform subsystems."""
    config = global_runtime_config_service.get_config()
    return global_health_monitor.evaluate_overall_health(
        db=db,
        kill_switch_active=config.kill_switch_enabled,
    )


@router.get("/status", response_model=PlatformStatusResponse)
def get_status() -> PlatformStatusResponse:
    """High-level platform status summary."""
    breakers = global_circuit_breaker_registry.list_all()
    open_count = sum(1 for b in breakers if b.state == "open")
    perf = global_performance_profiler.get_snapshot()
    config = global_runtime_config_service.get_config()

    return PlatformStatusResponse(
        environment=settings.app_env,
        status="critical" if open_count > 0 or config.kill_switch_enabled else "healthy",
        uptime_seconds=round(global_health_monitor._start_time, 2),
        active_circuit_breakers=len(breakers),
        open_circuit_breakers=open_count,
        runtime_config_version=config.version,
        total_cycles_executed=perf.throughput.total_cycles_executed,
    )


@router.get("/traces", response_model=list[TraceRecord])
def query_traces(
    trace_id: Annotated[uuid.UUID | None, Query()] = None,
    name: Annotated[str | None, Query()] = None,
    status_filter: Annotated[SpanStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[TraceRecord]:
    """Queries distributed execution traces from the in-memory trace collector."""
    return global_trace_collector.get_traces(
        trace_id=trace_id,
        name=name,
        status=status_filter,
        limit=limit,
    )


@router.get("/traces/{trace_id}", response_model=TraceRecord)
def get_trace_detail(trace_id: uuid.UUID) -> TraceRecord:
    """Fetches complete span timeline for a specific distributed trace."""
    trace = global_trace_collector.get_trace_by_id(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with ID '{trace_id}' not found",
        )
    return trace


@router.get("/audit", response_model=list[AuditRecord])
def query_audit_trail(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[str | None, Query()] = None,
    component: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[str | None, Query()] = None,
    correlation_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditRecord]:
    """Queries immutable audit logs."""
    return audit_service.get_history(
        actor=actor,
        component=component,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        limit=limit,
        db=db,
    )


@router.get("/logs", response_model=list[StructuredLogEntry])
def query_logs(
    level: Annotated[str | None, Query()] = None,
    correlation_id: Annotated[str | None, Query()] = None,
    cycle_id: Annotated[str | None, Query()] = None,
    trace_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[StructuredLogEntry]:
    """Queries recent structured JSON logs from the circular log buffer."""
    return global_log_buffer.get_entries(
        level=level,
        correlation_id=correlation_id,
        cycle_id=cycle_id,
        trace_id=trace_id,
        limit=limit,
    )


@router.get("/metrics/telemetry", response_model=PerformanceSnapshot)
def get_telemetry() -> PerformanceSnapshot:
    """Retrieves rolling latency percentiles, throughput rates, and resource utilization."""
    return global_performance_profiler.get_snapshot()


@router.get("/circuit-breakers", response_model=list[CircuitBreakerSnapshot])
def list_circuit_breakers() -> list[CircuitBreakerSnapshot]:
    """Lists status and failure counters for all registered circuit breakers."""
    return global_circuit_breaker_registry.list_all()


@router.post("/circuit-breakers/{name}/reset", response_model=CircuitBreakerResetResponse)
def reset_circuit_breaker(name: str) -> CircuitBreakerResetResponse:
    """Manually resets a circuit breaker back to CLOSED state."""
    breaker = global_circuit_breaker_registry.get_or_create(name)
    breaker.reset()
    return CircuitBreakerResetResponse(
        name=name,
        message="Circuit breaker successfully reset to CLOSED",
        snapshot=breaker.get_snapshot(),
    )


@router.get("/config", response_model=PlatformRuntimeConfig)
def get_runtime_config() -> PlatformRuntimeConfig:
    """Returns the current active dynamic runtime configuration."""
    return global_runtime_config_service.get_config()


@router.post("/config", response_model=PlatformRuntimeConfig)
def update_runtime_config(req: ConfigUpdateRequest) -> PlatformRuntimeConfig:
    """Updates runtime configuration dynamically with strict validation."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        return global_runtime_config_service.update_config(updates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/shutdown", response_model=ShutdownTriggerResponse)
def trigger_shutdown(timeout_seconds: Annotated[float, Query(ge=1.0, le=60.0)] = 10.0) -> ShutdownTriggerResponse:
    """Initiates an ordered graceful shutdown sequence."""
    result = global_shutdown_coordinator.execute_shutdown(timeout_seconds=timeout_seconds)
    return ShutdownTriggerResponse(result=result)
