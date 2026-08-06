"""Unit tests for the Graceful Shutdown Coordinator."""
from app.domains.platform.shutdown import GracefulShutdownCoordinator, ShutdownPhase


def test_graceful_shutdown_order():
    coordinator = GracefulShutdownCoordinator()
    events_called = []

    coordinator.register_scheduler_stop_hook(lambda: events_called.append("scheduler"))
    coordinator.register_pipeline_drain_hook(lambda: events_called.append("pipeline"))
    coordinator.register_event_flush_hook(lambda: events_called.append("event_bus"))
    coordinator.register_audit_flush_hook(lambda: events_called.append("audit"))

    res = coordinator.execute_shutdown(timeout_seconds=5.0)

    assert res.success is True
    assert events_called == ["scheduler", "pipeline", "event_bus", "audit"]
    assert ShutdownPhase.completed in res.completed_phases
