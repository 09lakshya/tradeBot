"""FastAPI dependencies for the Execution Orchestrator domain."""
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.service import ExecutionOrchestratorService
from app.domains.trading.clock import SystemClock

_global_event_bus: EventBus | None = None
_global_orchestrator_service: ExecutionOrchestratorService | None = None


def get_event_bus() -> EventBus:
    """Returns global singleton instance of the internal EventBus."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def get_orchestrator_service() -> ExecutionOrchestratorService:
    """Returns global singleton instance of the ExecutionOrchestratorService."""
    global _global_orchestrator_service
    if _global_orchestrator_service is None:
        _global_orchestrator_service = ExecutionOrchestratorService(
            clock=SystemClock(),
            event_bus=get_event_bus(),
        )
    return _global_orchestrator_service
