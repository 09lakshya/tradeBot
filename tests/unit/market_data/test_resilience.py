"""Retry, backoff, and rate-limit behaviour."""
import time

import pytest

from app.domains.market_data.providers.base import (
    ProviderDataError,
    ProviderTimeoutError,
)
from app.domains.market_data.providers.resilience import (
    RateLimiter,
    RetryPolicy,
    with_retry,
)


def test_retry_succeeds_after_transient_failures() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderTimeoutError("boom")
        return "ok"

    result = with_retry(flaky, policy=RetryPolicy(max_attempts=3, base_delay=0.01))
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_exhausts_and_raises() -> None:
    def always_fails() -> None:
        raise ProviderTimeoutError("nope")

    with pytest.raises(ProviderTimeoutError):
        with_retry(always_fails, policy=RetryPolicy(max_attempts=2, base_delay=0.01))


def test_non_transient_error_is_not_retried() -> None:
    calls = {"n": 0}

    def bad_data() -> None:
        calls["n"] += 1
        raise ProviderDataError("malformed")

    with pytest.raises(ProviderDataError):
        with_retry(bad_data, policy=RetryPolicy(max_attempts=5, base_delay=0.01))
    assert calls["n"] == 1, "bad data must fail fast, not retry"


def test_backoff_grows_exponentially() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=100.0, jitter=0.0)
    assert policy.delay_for(1) == pytest.approx(1.0)
    assert policy.delay_for(2) == pytest.approx(2.0)
    assert policy.delay_for(3) == pytest.approx(4.0)


def test_backoff_respects_max_delay() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=3.0, jitter=0.0)
    assert policy.delay_for(10) == pytest.approx(3.0)


def test_rate_limiter_allows_burst_then_throttles() -> None:
    limiter = RateLimiter(rate=1000, capacity=3)
    assert all(limiter.acquire(block=False) for _ in range(3))
    assert limiter.acquire(block=False) is False, "bucket should be empty after burst"


def test_rate_limiter_refills_over_time() -> None:
    limiter = RateLimiter(rate=100, capacity=1)
    assert limiter.acquire(block=False) is True
    assert limiter.acquire(block=False) is False
    time.sleep(0.05)  # 100/sec -> refilled well within this window
    assert limiter.acquire(block=False) is True
