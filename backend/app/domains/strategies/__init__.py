"""Strategy Engine Domain Package."""
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.composite import ComposedStrategyPipeline
from app.domains.strategies.enums import (
    MarketRegime,
    SignalDirection,
    SignalType,
    StrategyCategory,
    StrategyStatus,
)
from app.domains.strategies.exceptions import (
    DuplicateStrategyError,
    InvalidStrategyParameterError,
    StrategyExecutionError,
    StrategyLookAheadBiasError,
    StrategyNotFoundError,
    StrategyValidationError,
    StrategyVersionMismatchError,
)
from app.domains.strategies.models import (
    StrategyModel,
    StrategyParameterSnapshotModel,
    StrategySignalModel,
)
from app.domains.strategies.registry import StrategyRegistry, register_strategy
from app.domains.strategies.schemas import (
    ParameterSnapshotCreate,
    ParameterSnapshotResponse,
    StrategyCreate,
    StrategyMetadata,
    StrategyParameterValidationRequest,
    StrategyParameterValidationResponse,
    StrategyUpdate,
    TradingSignal,
)
from app.domains.strategies.service import StrategyService
import app.domains.strategies.builtin  # Auto-load all 21 builtins

__all__ = [
    "BaseStrategy",
    "StrategyContext",
    "ComposedStrategyPipeline",
    "StrategyRegistry",
    "register_strategy",
    "StrategyService",
    "StrategyCategory",
    "StrategyStatus",
    "SignalDirection",
    "SignalType",
    "MarketRegime",
    "TradingSignal",
    "StrategyMetadata",
    "StrategyCreate",
    "StrategyUpdate",
    "ParameterSnapshotCreate",
    "ParameterSnapshotResponse",
    "StrategyParameterValidationRequest",
    "StrategyParameterValidationResponse",
    "StrategyModel",
    "StrategyParameterSnapshotModel",
    "StrategySignalModel",
    "StrategyNotFoundError",
    "DuplicateStrategyError",
    "StrategyVersionMismatchError",
    "InvalidStrategyParameterError",
    "StrategyExecutionError",
    "StrategyValidationError",
    "StrategyLookAheadBiasError",
]
