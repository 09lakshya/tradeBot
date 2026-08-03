"""Resilience primitives for provider calls: token-bucket rate limiting and a
retry wrapper with exponential backoff + jitter.

Request *timeouts* are enforced inside each provider at the HTTP-client level
(e.g. ``requests.get(..., timeout=...)``); this module handles what happens
*around* the call — throttling, retrying transient failures, and surfacing
metrics. Kept dependency-free so it runs in tests without network or extras.
"""
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.logging import get_logger
from app.domains.market_data.providers.base import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

log = get_logger(__name__)

# Failures worth retrying — malformed data (ProviderDataError) is NOT retried.
_TRANSIENT = (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError)


class RateLimiter:
    """Thread-safe token bucket. ``rate`` tokens refill per second up to ``capacity``."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1, block: bool = True, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                needed = (tokens - self._tokens) / self._rate
            if not block or time.monotonic() + needed > deadline:
                return False
            time.sleep(min(needed, 0.25))


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5       # seconds
    max_delay: float = 8.0
    jitter: float = 0.2           # +/- fraction

    def delay_for(self, attempt: int) -> float:
        raw = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return raw * (1 + random.uniform(-self.jitter, self.jitter))


def with_retry[T](
    fn: Callable[..., T],
    *args: object,
    policy: RetryPolicy | None = None,
    on_attempt: Callable[[int, Exception | None], None] | None = None,
    **kwargs: object,
) -> T:
    """Call ``fn`` with retries on transient ProviderErrors and exponential backoff.

    ``on_attempt(attempt, error)`` is invoked after each try (error=None on success)
    so callers can record retry/latency metrics.
    """
    policy = policy or RetryPolicy()
    last_exc: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = fn(*args, **kwargs)
            if on_attempt:
                on_attempt(attempt, None)
            return result
        except _TRANSIENT as exc:
            last_exc = exc
            if on_attempt:
                on_attempt(attempt, exc)
            if attempt == policy.max_attempts:
                break
            delay = policy.delay_for(attempt)
            log.warning(
                "provider_retry", fn=getattr(fn, "__name__", str(fn)),
                attempt=attempt, delay=round(delay, 3), error=str(exc),
            )
            time.sleep(delay)
        except ProviderError:
            raise  # non-transient (e.g. bad data) — fail fast, no retry
    assert last_exc is not None
    raise last_exc
