"""Unit tests for the Configurable Retry Engine."""
import pytest
from app.domains.platform.exceptions import MarketDataTimeoutError, PreTradeRiskViolationError
from app.domains.platform.retry import (
    ExponentialBackoffRetryPolicy,
    FixedDelayRetryPolicy,
    RetryExecutor,
    retryable,
)


def test_retry_success_after_transient_failures():
    attempts = 0

    @retryable(policy=FixedDelayRetryPolicy(max_retries=3, delay_seconds=0.01))
    def flaky_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Network dropped")
        return "success"

    result = flaky_operation()
    assert result == "success"
    assert attempts == 3


def test_retry_aborts_on_non_retryable_risk_violation():
    attempts = 0

    @retryable(policy=FixedDelayRetryPolicy(max_retries=5, delay_seconds=0.01))
    def risk_checked_call() -> str:
        nonlocal attempts
        attempts += 1
        raise PreTradeRiskViolationError("hard_limit", "INFY", "Exceeded max drawdown")

    with pytest.raises(PreTradeRiskViolationError):
        risk_checked_call()

    # Must fail immediately without retrying
    assert attempts == 1


def test_retry_exhaustion():
    attempts = 0

    @retryable(policy=FixedDelayRetryPolicy(max_retries=2, delay_seconds=0.01))
    def always_failing() -> str:
        nonlocal attempts
        attempts += 1
        raise MarketDataTimeoutError("NIFTY50", 2.0)

    with pytest.raises(MarketDataTimeoutError):
        always_failing()

    # Initial attempt + 2 retries = 3 attempts total
    assert attempts == 3


def test_exponential_backoff_delays():
    policy = ExponentialBackoffRetryPolicy(
        initial_delay_seconds=0.1,
        max_delay_seconds=1.0,
        backoff_factor=2.0,
        jitter=False,
    )
    assert policy.get_delay(1) == 0.1
    assert policy.get_delay(2) == 0.2
    assert policy.get_delay(3) == 0.4
    assert policy.get_delay(4) == 0.8
    assert policy.get_delay(5) == 1.0  # Capped at max_delay_seconds
