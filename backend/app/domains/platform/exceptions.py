"""Centralized Domain Exception Hierarchy and RFC 7807 Problem Details Support."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.domains.platform.logging import correlation_id_ctx, trace_id_ctx


class PlatformException(Exception):
    """Base exception for all trading platform domain and infrastructure errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "PLATFORM_ERROR",
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
        http_status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.is_retryable = is_retryable
        self.details = details or {}
        self.http_status_code = http_status_code
        self.timestamp = datetime.now(UTC).isoformat()
        self.trace_id = trace_id_ctx.get()
        self.correlation_id = correlation_id_ctx.get()

    def to_problem_details(self) -> dict[str, Any]:
        """Formats the exception into an RFC 7807 compliant problem details dictionary."""
        return {
            "type": f"https://tradebot.internal/errors/{self.error_code.lower()}",
            "title": self.error_code,
            "status": self.http_status_code,
            "detail": self.message,
            "instance": f"/errors/{uuid.uuid4()}",
            "is_retryable": self.is_retryable,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# -------------------------------------------------------------------------
# Market Data Domain Exceptions
# -------------------------------------------------------------------------
class MarketDataException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "MARKET_DATA_ERROR")
        kwargs.setdefault("http_status_code", 502)
        super().__init__(message, **kwargs)


class MarketDataProviderUnavailableError(MarketDataException):
    def __init__(self, provider: str, message: str = "Market data provider unreachable") -> None:
        super().__init__(
            f"Provider '{provider}' unavailable: {message}",
            error_code="MARKET_DATA_PROVIDER_UNAVAILABLE",
            is_retryable=True,
            details={"provider": provider},
        )


class MarketDataTimeoutError(MarketDataException):
    def __init__(self, symbol: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Market data request for '{symbol}' timed out after {timeout_seconds}s",
            error_code="MARKET_DATA_TIMEOUT",
            is_retryable=True,
            details={"symbol": symbol, "timeout_seconds": timeout_seconds},
            http_status_code=504,
        )


class MarketDataRateLimitError(MarketDataException):
    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(
            f"Rate limit exceeded for provider '{provider}'",
            error_code="MARKET_DATA_RATE_LIMIT_EXCEEDED",
            is_retryable=True,
            details={"provider": provider, "retry_after": retry_after},
            http_status_code=429,
        )


class InvalidSymbolError(MarketDataException):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"Instrument symbol '{symbol}' is invalid or unknown",
            error_code="INVALID_SYMBOL",
            is_retryable=False,
            details={"symbol": symbol},
            http_status_code=400,
        )


# -------------------------------------------------------------------------
# Strategy Domain Exceptions
# -------------------------------------------------------------------------
class StrategyException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "STRATEGY_ERROR")
        kwargs.setdefault("http_status_code", 422)
        super().__init__(message, **kwargs)


class StrategyEvaluationError(StrategyException):
    def __init__(self, strategy_id: str, reason: str) -> None:
        super().__init__(
            f"Evaluation failed for strategy '{strategy_id}': {reason}",
            error_code="STRATEGY_EVALUATION_FAILED",
            is_retryable=False,
            details={"strategy_id": strategy_id, "reason": reason},
        )


class LookAheadBiasError(StrategyException):
    def __init__(self, strategy_id: str, requested_time: str, current_time: str) -> None:
        super().__init__(
            f"Look-ahead bias violation in '{strategy_id}': requested {requested_time} > current {current_time}",
            error_code="LOOK_AHEAD_BIAS_VIOLATION",
            is_retryable=False,
            details={"strategy_id": strategy_id, "requested_time": requested_time, "current_time": current_time},
        )


# -------------------------------------------------------------------------
# Pre-Trade Risk Domain Exceptions
# -------------------------------------------------------------------------
class RiskException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "RISK_ERROR")
        kwargs.setdefault("is_retryable", False)  # Risk violations are NEVER retryable
        kwargs.setdefault("http_status_code", 403)
        super().__init__(message, **kwargs)


class PreTradeRiskViolationError(RiskException):
    def __init__(self, rule_name: str, symbol: str, reason: str) -> None:
        super().__init__(
            f"Pre-trade risk rule '{rule_name}' rejected order for '{symbol}': {reason}",
            error_code="PRE_TRADE_RISK_VIOLATION",
            details={"rule_name": rule_name, "symbol": symbol, "reason": reason},
        )


class KillSwitchActiveError(RiskException):
    def __init__(self, reason: str = "Trading halted by master risk kill switch") -> None:
        super().__init__(
            reason,
            error_code="KILL_SWITCH_ACTIVE",
            details={"reason": reason},
        )


# -------------------------------------------------------------------------
# Portfolio Construction Exceptions
# -------------------------------------------------------------------------
class PortfolioException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "PORTFOLIO_CONSTRUCTION_ERROR")
        kwargs.setdefault("http_status_code", 422)
        super().__init__(message, **kwargs)


class PortfolioOptimizationError(PortfolioException):
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Portfolio optimization solver failed: {reason}",
            error_code="PORTFOLIO_OPTIMIZATION_FAILED",
            is_retryable=False,
            details={"reason": reason},
        )


# -------------------------------------------------------------------------
# OMS & Trading Domain Exceptions
# -------------------------------------------------------------------------
class OMSException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "OMS_ERROR")
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("http_status_code", 400)
        super().__init__(message, **kwargs)


class InsufficientBuyingPowerError(OMSException):
    def __init__(self, required: str, available: str) -> None:
        super().__init__(
            f"Insufficient buying power: required {required}, available {available}",
            error_code="INSUFFICIENT_BUYING_POWER",
            details={"required": required, "available": available},
        )


class LedgerInvariantDiscrepancyError(OMSException):
    def __init__(self, discrepancy: str) -> None:
        super().__init__(
            f"Double-entry ledger invariant violation detected: {discrepancy}",
            error_code="LEDGER_INVARIANT_VIOLATION",
            http_status_code=500,
            details={"discrepancy": discrepancy},
        )


# -------------------------------------------------------------------------
# Execution & Orchestration Exceptions
# -------------------------------------------------------------------------
class ExecutionException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "EXECUTION_ERROR")
        kwargs.setdefault("http_status_code", 500)
        super().__init__(message, **kwargs)


class SchedulerException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "SCHEDULER_ERROR")
        kwargs.setdefault("http_status_code", 500)
        super().__init__(message, **kwargs)


# -------------------------------------------------------------------------
# Infrastructure & Resilience Exceptions
# -------------------------------------------------------------------------
class InfrastructureException(PlatformException):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("error_code", "INFRASTRUCTURE_ERROR")
        kwargs.setdefault("is_retryable", True)
        kwargs.setdefault("http_status_code", 503)
        super().__init__(message, **kwargs)


class DatabaseConnectionError(InfrastructureException):
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Database connectivity failure: {reason}",
            error_code="DATABASE_CONNECTION_ERROR",
            is_retryable=True,
            details={"reason": reason},
        )


class CircuitBreakerOpenError(InfrastructureException):
    def __init__(self, breaker_name: str, reset_timeout_seconds: float) -> None:
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN. Requests blocked for {reset_timeout_seconds}s",
            error_code="CIRCUIT_BREAKER_OPEN",
            is_retryable=False,
            details={"breaker_name": breaker_name, "reset_timeout_seconds": reset_timeout_seconds},
        )
