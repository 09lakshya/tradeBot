"""Unit tests for Centralized Domain Exception Hierarchy and RFC 7807 Problem Details."""
from app.domains.platform.exceptions import (
    CircuitBreakerOpenError,
    InsufficientBuyingPowerError,
    InvalidSymbolError,
    KillSwitchActiveError,
    LookAheadBiasError,
    MarketDataTimeoutError,
    PlatformException,
    PreTradeRiskViolationError,
)


def test_platform_exception_problem_details():
    exc = PlatformException(
        "Generic system error",
        error_code="INTERNAL_ERROR",
        is_retryable=False,
        details={"sub": "core"},
        http_status_code=500,
    )
    pd = exc.to_problem_details()
    assert pd["title"] == "INTERNAL_ERROR"
    assert pd["status"] == 500
    assert pd["detail"] == "Generic system error"
    assert pd["is_retryable"] is False
    assert pd["details"]["sub"] == "core"


def test_market_data_exceptions():
    to_exc = MarketDataTimeoutError("TCS", 5.0)
    assert to_exc.is_retryable is True
    assert to_exc.http_status_code == 504
    assert to_exc.details["symbol"] == "TCS"

    sym_exc = InvalidSymbolError("INVALID_TICKER")
    assert sym_exc.is_retryable is False
    assert sym_exc.http_status_code == 400


def test_risk_exceptions_never_retryable():
    risk_exc = PreTradeRiskViolationError("max_order_size", "RELIANCE", "Order size 10000 exceeds 500 limit")
    assert risk_exc.is_retryable is False
    assert risk_exc.http_status_code == 403

    kill_exc = KillSwitchActiveError()
    assert kill_exc.is_retryable is False


def test_oms_and_circuit_breaker_exceptions():
    bp_exc = InsufficientBuyingPowerError("50000.00", "25000.00")
    assert bp_exc.is_retryable is False

    cb_exc = CircuitBreakerOpenError("market_data", 25.0)
    assert cb_exc.is_retryable is False
    assert cb_exc.details["breaker_name"] == "market_data"
