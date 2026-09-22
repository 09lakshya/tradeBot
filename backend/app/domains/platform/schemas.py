"""Platform Domain Pydantic Request & Response Schemas for Monitoring REST APIs."""
from __future__ import annotations

from pydantic import BaseModel

from app.domains.platform.circuit_breaker import CircuitBreakerSnapshot
from app.domains.platform.shutdown import ShutdownResult


class PlatformStatusResponse(BaseModel):
    """Overall platform status summary."""
    environment: str
    status: str
    uptime_seconds: float
    active_circuit_breakers: int
    open_circuit_breakers: int
    runtime_config_version: int
    total_cycles_executed: int


class ConfigUpdateRequest(BaseModel):
    """Dynamic configuration update request."""
    max_active_orders: int | None = None
    cycle_interval_seconds: float | None = None
    max_single_order_pct: float | None = None
    max_portfolio_leverage: float | None = None
    circuit_breaker_failure_threshold: int | None = None
    circuit_breaker_recovery_seconds: float | None = None
    retry_max_attempts: int | None = None
    logging_level: str | None = None
    kill_switch_enabled: bool | None = None
    enable_paper_fill_simulation: bool | None = None


class CircuitBreakerResetResponse(BaseModel):
    name: str
    message: str
    snapshot: CircuitBreakerSnapshot


class ShutdownTriggerResponse(BaseModel):
    result: ShutdownResult
