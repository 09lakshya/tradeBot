"""Configurable Retry Engine with Exponential Backoff, Jitter, and Domain Safety Gates."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import wraps
import inspect
import random
import time
from typing import Any, Callable, Sequence, TypeVar

from app.domains.platform.exceptions import PlatformException, RiskException
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger("platform.retry")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class RetryPolicy:
    """Base specification for operation retry behaviors."""
    max_retries: int = 3

    def get_delay(self, attempt: int) -> float:
        raise NotImplementedError


@dataclass(frozen=True)
class FixedDelayRetryPolicy(RetryPolicy):
    """Fixed delay retry policy."""
    delay_seconds: float = 0.5

    def get_delay(self, attempt: int) -> float:
        return self.delay_seconds


@dataclass(frozen=True)
class ExponentialBackoffRetryPolicy(RetryPolicy):
    """Exponential backoff policy with full jitter to avoid herd stampedes."""
    initial_delay_seconds: float = 0.1
    max_delay_seconds: float = 5.0
    backoff_factor: float = 2.0
    jitter: bool = True

    def get_delay(self, attempt: int) -> float:
        delay = min(
            self.max_delay_seconds,
            self.initial_delay_seconds * (self.backoff_factor ** (attempt - 1)),
        )
        if self.jitter:
            delay = random.uniform(0.0, delay)
        return delay


class RetryExecutor:
    """Executes callables under configured retry policies with domain safety invariants."""

    @staticmethod
    def is_exception_retryable(
        exc: Exception,
        retryable_types: Sequence[type[Exception]] | None = None,
        non_retryable_types: Sequence[type[Exception]] | None = None,
    ) -> bool:
        # 1. Explicit risk and business rule safety: Risk rejections are NEVER retryable
        if isinstance(exc, RiskException):
            return False

        # 2. Check PlatformException retryable flag
        if isinstance(exc, PlatformException) and not exc.is_retryable:
            return False

        # 3. Check explicit non-retryable types
        if non_retryable_types and any(isinstance(exc, t) for t in non_retryable_types):
            return False

        # 4. Check explicit retryable types
        if retryable_types:
            return any(isinstance(exc, t) for t in retryable_types)

        # 5. Default: PlatformException with is_retryable=True or standard transient connection errors
        if isinstance(exc, PlatformException):
            return exc.is_retryable

        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True

        return False

    @classmethod
    def execute_sync(
        cls,
        fn: Callable[..., T],
        *args: Any,
        policy: RetryPolicy = ExponentialBackoffRetryPolicy(),
        retryable_types: Sequence[type[Exception]] | None = None,
        non_retryable_types: Sequence[type[Exception]] | None = None,
        operation_name: str | None = None,
        **kwargs: Any,
    ) -> T:
        op = operation_name or fn.__name__
        attempt = 1

        while True:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if attempt > policy.max_retries or not cls.is_exception_retryable(exc, retryable_types, non_retryable_types):
                    log.warning(
                        "operation_retry_aborted",
                        operation=op,
                        attempt=attempt,
                        max_retries=policy.max_retries,
                        error=str(exc),
                        is_retryable=cls.is_exception_retryable(exc, retryable_types, non_retryable_types),
                    )
                    raise

                delay = policy.get_delay(attempt)
                log.info(
                    "operation_retry_attempt",
                    operation=op,
                    attempt=attempt,
                    max_retries=policy.max_retries,
                    delay_seconds=delay,
                    error=str(exc),
                )
                time.sleep(delay)
                attempt += 1

    @classmethod
    async def execute_async(
        cls,
        fn: Callable[..., Any],
        *args: Any,
        policy: RetryPolicy = ExponentialBackoffRetryPolicy(),
        retryable_types: Sequence[type[Exception]] | None = None,
        non_retryable_types: Sequence[type[Exception]] | None = None,
        operation_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        op = operation_name or fn.__name__
        attempt = 1

        while True:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                if attempt > policy.max_retries or not cls.is_exception_retryable(exc, retryable_types, non_retryable_types):
                    log.warning(
                        "operation_retry_aborted",
                        operation=op,
                        attempt=attempt,
                        max_retries=policy.max_retries,
                        error=str(exc),
                        is_retryable=cls.is_exception_retryable(exc, retryable_types, non_retryable_types),
                    )
                    raise

                delay = policy.get_delay(attempt)
                log.info(
                    "operation_retry_attempt",
                    operation=op,
                    attempt=attempt,
                    max_retries=policy.max_retries,
                    delay_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
                attempt += 1


def retryable(
    policy: RetryPolicy = ExponentialBackoffRetryPolicy(),
    retryable_types: Sequence[type[Exception]] | None = None,
    non_retryable_types: Sequence[type[Exception]] | None = None,
    name: str | None = None,
) -> Callable[[F], F]:
    """Decorator to apply retry logic to a synchronous or asynchronous function."""
    def decorator(fn: F) -> F:
        op_name = name or fn.__name__

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return RetryExecutor.execute_sync(
                fn,
                *args,
                policy=policy,
                retryable_types=retryable_types,
                non_retryable_types=non_retryable_types,
                operation_name=op_name,
                **kwargs,
            )

        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await RetryExecutor.execute_async(
                fn,
                *args,
                policy=policy,
                retryable_types=retryable_types,
                non_retryable_types=non_retryable_types,
                operation_name=op_name,
                **kwargs,
            )

        if inspect.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
