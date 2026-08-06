"""Domain Enums for Strategy Engine."""
from enum import Enum


class StrategyStatus(str, Enum):
    """Lifecycle status of a strategy."""
    active = "active"
    inactive = "inactive"
    deprecated = "deprecated"
    testing = "testing"


class SignalType(str, Enum):
    """Actionable category of a generated trading signal."""
    entry_long = "entry_long"
    entry_short = "entry_short"
    exit_long = "exit_long"
    exit_short = "exit_short"
    rebalance = "rebalance"
    hold = "hold"


class SignalDirection(str, Enum):
    """Directional bias of a signal."""
    long = "long"
    short = "short"
    flat = "flat"


class MarketRegime(str, Enum):
    """Detected market regime context at signal generation."""
    trending_bullish = "trending_bullish"
    trending_bearish = "trending_bearish"
    ranging = "ranging"
    volatile_expansion = "volatile_expansion"
    low_volatility_consolidation = "low_volatility_consolidation"
    unknown = "unknown"


class StrategyCategory(str, Enum):
    """Classification taxonomy for trading strategies."""
    trend_following = "trend_following"
    momentum = "momentum"
    mean_reversion = "mean_reversion"
    volatility = "volatility"
    volume = "volume"
    price_action = "price_action"
    institutional = "institutional"
    multi_factor = "multi_factor"
    composite = "composite"
    custom = "custom"
