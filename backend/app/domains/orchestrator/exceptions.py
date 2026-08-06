"""Exceptions for the Execution Orchestrator domain."""
from typing import Any


class OrchestratorException(Exception):
    """Base exception for the execution orchestrator domain."""


class PipelineExecutionError(OrchestratorException):
    """Raised when an error occurs during an execution pipeline stage."""

    def __init__(self, stage: str, message: str, details: dict[str, Any] | None = None):
        self.stage = stage
        self.details = details or {}
        super().__init__(f"Pipeline failure in stage '{stage}': {message}")


class MarketClosedError(OrchestratorException):
    """Raised when an execution cycle is attempted outside allowed market hours."""

    def __init__(self, message: str = "Market is currently closed for execution"):
        super().__init__(message)


class HolidaySessionError(MarketClosedError):
    """Raised when market execution is attempted on a market holiday."""

    def __init__(self, holiday_name: str, date_str: str):
        self.holiday_name = holiday_name
        self.date_str = date_str
        super().__init__(f"Market is closed today for {holiday_name} ({date_str})")


class InvariantViolationError(OrchestratorException):
    """Raised when a continuous invariant check (cash, ledger, positions, risk) fails."""

    def __init__(self, invariant_name: str, message: str, discrepancies: dict[str, Any] | None = None):
        self.invariant_name = invariant_name
        self.discrepancies = discrepancies or {}
        super().__init__(f"CRITICAL Invariant breach on '{invariant_name}': {message}")


class SchedulerError(OrchestratorException):
    """Raised when scheduler configuration, startup, or task dispatch fails."""


class ServiceUnavailableError(OrchestratorException):
    """Raised when a dependent domain service or database connection is unreachable."""
