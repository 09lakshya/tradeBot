"""Unit tests for the Multi-State Circuit Breaker Subsystem."""
import time
import pytest
from app.domains.platform.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitBreakerState,
)
from app.domains.platform.exceptions import CircuitBreakerOpenError


def test_circuit_breaker_closed_state():
    cb = CircuitBreaker("test_cb", failure_threshold=3, recovery_timeout_seconds=0.1)
    assert cb.state == CircuitBreakerState.closed

    # Successful calls keep state closed
    with cb.protect():
        pass
    assert cb.state == CircuitBreakerState.closed


def test_circuit_breaker_trips_to_open():
    cb = CircuitBreaker("test_tripper", failure_threshold=3, recovery_timeout_seconds=0.1)

    for _ in range(3):
        try:
            with cb.protect():
                raise ConnectionResetError("Connection died")
        except ConnectionResetError:
            pass

    assert cb.state == CircuitBreakerState.open

    # Further calls fail immediately with CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        with cb.protect():
            pass

    assert exc_info.value.details["breaker_name"] == "test_tripper"


def test_circuit_breaker_half_open_recovery():
    cb = CircuitBreaker(
        "test_recovery",
        failure_threshold=2,
        recovery_timeout_seconds=0.05,
        half_open_success_threshold=2,
    )

    # Trip breaker
    for _ in range(2):
        try:
            with cb.protect():
                raise TimeoutError("Timeout")
        except TimeoutError:
            pass

    assert cb.state == CircuitBreakerState.open

    # Wait for recovery timeout
    time.sleep(0.06)
    assert cb.state == CircuitBreakerState.half_open

    # 1st probe success
    with cb.protect():
        pass
    assert cb.state == CircuitBreakerState.half_open

    # 2nd probe success -> back to closed
    with cb.protect():
        pass
    assert cb.state == CircuitBreakerState.closed


def test_circuit_breaker_manual_reset():
    cb = CircuitBreaker("test_reset", failure_threshold=1)
    try:
        with cb.protect():
            raise RuntimeError("Failure")
    except RuntimeError:
        pass

    assert cb.state == CircuitBreakerState.open
    cb.reset()
    assert cb.state == CircuitBreakerState.closed


def test_circuit_breaker_registry():
    reg = CircuitBreakerRegistry()
    b1 = reg.get_or_create("feed_alpha", failure_threshold=5)
    b2 = reg.get_or_create("feed_alpha")
    assert b1 is b2

    all_breakers = reg.list_all()
    assert len(all_breakers) == 1
    assert all_breakers[0].name == "feed_alpha"
