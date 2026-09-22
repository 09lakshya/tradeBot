"""Subsystem health monitoring, latency probes, and fault diagnostics."""
import logging
import time
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.orchestrator.schemas import HealthMetricsResponse, SubsystemHealth
from app.domains.trading.clock import Clock, SystemClock

log = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors performance latencies, staleness, and operational health of all subsystems."""

    def __init__(self, clock: Clock | None = None):
        self.clock = clock or SystemClock()
        self._latencies: dict[str, float] = {}
        self._last_checks: dict[str, datetime] = {}
        self._subsystem_status: dict[str, str] = {}

    def record_stage_latency(self, stage_name: str, latency_ms: float) -> None:
        """Records an execution latency observation for a pipeline stage."""
        self._latencies[stage_name] = latency_ms
        self._last_checks[stage_name] = self.clock.now()
        # Classification
        if latency_ms < 50.0:
            self._subsystem_status[stage_name] = "healthy"
        elif latency_ms < 150.0:
            self._subsystem_status[stage_name] = "degraded"
        else:
            self._subsystem_status[stage_name] = "unhealthy"

    def probe_database(self, db: Session) -> SubsystemHealth:
        """Probes database connection and measures round-trip query latency."""
        t0 = time.perf_counter()
        try:
            db.execute(text("SELECT 1"))
            latency_ms = (time.perf_counter() - t0) * 1000.0
            status = "healthy" if latency_ms < 20.0 else "degraded"
            health = SubsystemHealth(
                status=status,
                latency_ms=round(latency_ms, 3),
                last_check=self.clock.now(),
                details={"db_driver": str(db.bind.dialect.name) if db.bind else "unknown"},
            )
        except Exception as err:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            health = SubsystemHealth(
                status="unhealthy",
                latency_ms=round(latency_ms, 3),
                last_check=self.clock.now(),
                details={"error": str(err)},
            )
        self._latencies["database"] = health.latency_ms
        self._subsystem_status["database"] = health.status
        self._last_checks["database"] = health.last_check
        return health

    def get_health_report(self, db: Session | None = None) -> HealthMetricsResponse:
        """Generates a complete diagnostic health summary across all monitored components."""
        subsystems: dict[str, SubsystemHealth] = {}

        if db is not None:
            subsystems["database"] = self.probe_database(db)

        now = self.clock.now()
        tracked_components = [
            ("market_data", 10.0),
            ("strategies", 25.0),
            ("portfolio_construction", 15.0),
            ("risk_engine", 10.0),
            ("oms_orders", 15.0),
            ("simulator", 10.0),
            ("ledger", 10.0),
        ]

        for comp, target_ms in tracked_components:
            lat = self._latencies.get(comp, 0.0)
            status = self._subsystem_status.get(comp, "healthy")
            subsystems[comp] = SubsystemHealth(
                status=status,
                latency_ms=round(lat, 3),
                last_check=self._last_checks.get(comp, now),
                details={"target_latency_ms": target_ms},
            )

        # Overall health
        statuses = [s.status for s in subsystems.values()]
        if "unhealthy" in statuses:
            overall = "unhealthy"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        return HealthMetricsResponse(
            overall_status=overall,
            timestamp=now,
            subsystems=subsystems,
            total_pipeline_latency_target_ms=100.0,
        )
