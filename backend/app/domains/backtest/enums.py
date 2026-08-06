"""Backtest domain enumerations."""
import enum


class BacktestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BacktestSegmentType(str, enum.Enum):
    full = "full"
    in_sample = "in_sample"
    out_of_sample = "out_of_sample"
    walk_forward = "walk_forward"
    cross_validation = "cross_validation"
    monte_carlo = "monte_carlo"


class SlippageModelType(str, enum.Enum):
    fixed_bps = "fixed_bps"
    spread_pct = "spread_pct"
    volume_share = "volume_share"
    square_root_impact = "square_root_impact"


class ValidationMethod(str, enum.Enum):
    standard = "standard"
    walk_forward = "walk_forward"
    purged_cv = "purged_cv"
    combinatorial_purged_cv = "combinatorial_purged_cv"


class WindowType(str, enum.Enum):
    rolling = "rolling"
    expanding = "expanding"  # anchored


class BenchmarkSymbol(str, enum.Enum):
    NIFTY_50 = "^NSEI"
    NIFTY_BANK = "^NSEBANK"
    NIFTY_NEXT_50 = "^NSMIDCP"
    SENSEX = "^BSESN"
    CUSTOM = "CUSTOM"


class EventPriority(int, enum.Enum):
    """Deterministic event priority for same-timestamp event ordering.
    Lower number = higher priority = processed earlier.
    """
    TIMER = 10               # Session open/close, MTM valuation triggers
    CORPORATE_ACTION = 20    # Stock splits, dividends, bonuses
    MARKET_DATA = 30         # OHLCV bars & ticks
    STRATEGY_SIGNAL = 40     # Strategy signal evaluation
    ORDER_SUBMISSION = 50    # OMS order placement & pre-trade risk evaluation
    FILL_EXECUTION = 60      # Execution simulator fills at next bar open
