"""Domain Exceptions for Strategy Engine."""
from typing import Any
import uuid


class StrategyError(Exception):
    """Base exception for all strategy engine errors."""
    pass


class StrategyNotFoundError(StrategyError):
    """Raised when a requested strategy ID is not found in registry."""
    def __init__(self, strategy_id: str):
        super().__init__(f"Strategy '{strategy_id}' is not registered.")
        self.strategy_id = strategy_id


class DuplicateStrategyError(StrategyError):
    """Raised when attempting to register a strategy ID with an existing version."""
    def __init__(self, strategy_id: str, version: str):
        super().__init__(f"Strategy '{strategy_id}' version '{version}' is already registered.")
        self.strategy_id = strategy_id
        self.version = version


class InvalidStrategyParameterError(StrategyError):
    """Raised when strategy parameters fail schema or range validation."""
    def __init__(self, strategy_id: str, parameter_name: str, value: Any, reason: str):
        super().__init__(
            f"Invalid parameter '{parameter_name}'={value} for strategy '{strategy_id}': {reason}"
        )
        self.strategy_id = strategy_id
        self.parameter_name = parameter_name
        self.value = value
        self.reason = reason


class StrategyExecutionError(StrategyError):
    """Raised when an unhandled error occurs during strategy signal evaluation."""
    def __init__(self, strategy_id: str, message: str, original_exception: Exception | None = None):
        super().__init__(f"Execution error in strategy '{strategy_id}': {message}")
        self.strategy_id = strategy_id
        self.original_exception = original_exception


class StrategyVersionMismatchError(StrategyError):
    """Raised when attempting to run a strategy with an incompatible version snapshot."""
    def __init__(self, strategy_id: str, expected_version: str, found_version: str):
        super().__init__(
            f"Strategy '{strategy_id}' version mismatch: expected {expected_version}, found {found_version}"
        )
        self.strategy_id = strategy_id
        self.expected_version = expected_version
        self.found_version = found_version


class StrategyValidationError(StrategyError):
    """Raised when strategy definition or parameter payload fails validation."""
    def __init__(self, message: str):
        super().__init__(message)


class StrategyLookAheadBiasError(StrategyError):
    """Raised when a strategy attempts to access market data or context beyond current point-in-time."""
    def __init__(self, requested_time: str, current_time: str):
        super().__init__(
            f"Look-Ahead Bias Violation: Attempted to access data at {requested_time} when current clock is {current_time}"
        )
        self.requested_time = requested_time
        self.current_time = current_time
