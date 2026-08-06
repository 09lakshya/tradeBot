"""Unit tests for Multi-Subsystem Health Monitoring."""
from app.domains.platform.circuit_breaker import global_circuit_breaker_registry
from app.domains.platform.health import HealthMonitor, HealthStatus


def test_health_monitor_evaluation_nominal():
    monitor = HealthMonitor()
    report = monitor.evaluate_overall_health(db=None, kill_switch_active=False)

    # In standalone test env, redis may be degraded (not critical)
    assert report.overall_status in (HealthStatus.healthy, HealthStatus.degraded)
    assert "database" in report.subsystems
    assert "market_data" in report.subsystems
    assert "risk_engine" in report.subsystems
    assert "oms" in report.subsystems
    assert "portfolio_construction" in report.subsystems


def test_health_monitor_kill_switch_critical():
    monitor = HealthMonitor()
    report = monitor.evaluate_overall_health(db=None, kill_switch_active=True)

    assert report.overall_status == HealthStatus.critical
    assert report.subsystems["risk_engine"].status == HealthStatus.critical
    assert "kill switch" in (report.subsystems["risk_engine"].error_message or "").lower()


def test_health_monitor_open_circuit_breaker_critical():
    cb = global_circuit_breaker_registry.get_or_create("market_data_feed")
    cb.trip(reason="Trip")

    monitor = HealthMonitor()
    report = monitor.evaluate_overall_health(db=None)
    assert report.overall_status == HealthStatus.critical
    assert report.subsystems["market_data"].status == HealthStatus.critical

    cb.reset()
