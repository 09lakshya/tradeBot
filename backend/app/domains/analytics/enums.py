"""Domain enumerations for the Analytics & Paper Trading Validation engine."""
from __future__ import annotations

import enum


class MarketRegimeClassification(str, enum.Enum):
    """Broad market regime categories for trade classification."""
    trending = "trending"
    sideways = "sideways"
    high_volatility = "high_volatility"
    low_volatility = "low_volatility"
    bullish = "bullish"
    bearish = "bearish"
    unknown = "unknown"


class ExitReason(str, enum.Enum):
    """Reason a trade was closed."""
    stop_loss = "stop_loss"
    take_profit = "take_profit"
    trailing_stop = "trailing_stop"
    signal_exit = "signal_exit"
    time_exit = "time_exit"
    manual = "manual"
    risk_override = "risk_override"
    strategy_exit = "strategy_exit"
    rebalance = "rebalance"
    unknown = "unknown"


class ReportPeriod(str, enum.Enum):
    """Reporting frequency."""
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class AlertSeverity(str, enum.Enum):
    """Alert urgency classification."""
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertType(str, enum.Enum):
    """Operational alert categories."""
    large_drawdown = "large_drawdown"
    losing_streak = "losing_streak"
    high_exposure = "high_exposure"
    low_win_rate = "low_win_rate"
    strategy_degradation = "strategy_degradation"
    large_slippage = "large_slippage"
    high_costs = "high_costs"
    capital_utilization = "capital_utilization"
    portfolio_imbalance = "portfolio_imbalance"


class BenchmarkIndex(str, enum.Enum):
    """Supported benchmark indices for comparison."""
    nifty_50 = "nifty_50"
    nifty_next_50 = "nifty_next_50"
    sensex = "sensex"
    custom = "custom"
