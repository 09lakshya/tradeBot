"""Backtest domain exceptions."""
from datetime import datetime
import uuid


class BacktestError(Exception):
    """Base exception for all backtest domain errors."""
    pass


class LookAheadBiasError(BacktestError):
    """Raised when a component requests market data ahead of the current simulation clock."""

    def __init__(self, requested_time: datetime, current_clock: datetime, instrument_id: uuid.UUID | None = None):
        self.requested_time = requested_time
        self.current_clock = current_clock
        self.instrument_id = instrument_id
        msg = (
            f"Look-Ahead Bias Violation: Component attempted to access market data at {requested_time.isoformat()} "
            f"while current simulation clock is at {current_clock.isoformat()}"
        )
        if instrument_id:
            msg += f" for instrument {instrument_id}"
        super().__init__(msg)


class DataUnavailableError(BacktestError):
    """Raised when required historical data is missing or incomplete for a backtest interval."""

    def __init__(self, instrument_id: uuid.UUID | str, start: datetime, end: datetime, reason: str = ""):
        self.instrument_id = instrument_id
        self.start = start
        self.end = end
        msg = f"Market data unavailable for instrument {instrument_id} from {start.isoformat()} to {end.isoformat()}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


class InvalidWindowSpecError(BacktestError):
    """Raised when walk-forward or cross-validation window specifications are invalid."""

    def __init__(self, message: str):
        super().__init__(f"Invalid window specification: {message}")


class BacktestExecutionError(BacktestError):
    """Raised when an error occurs during backtest execution loop."""

    def __init__(self, backtest_id: uuid.UUID, message: str, original_exception: Exception | None = None):
        self.backtest_id = backtest_id
        self.original_exception = original_exception
        super().__init__(f"Backtest {backtest_id} failed during execution: {message}")
