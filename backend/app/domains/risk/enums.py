"""Risk Domain Enumerations."""
import enum


class RiskDecision(str, enum.Enum):
    """Outcome of an individual rule or complete pre-trade risk evaluation."""
    passed = "passed"
    blocked = "blocked"


class RuleType(str, enum.Enum):
    """Enumeration of all active pre-trade risk rules."""
    sanity = "sanity"
    kill_switch = "kill_switch"
    circuit_breaker = "circuit_breaker"
    buying_power = "buying_power"
    position_sizing = "position_sizing"
    exposure_limit = "exposure_limit"
    correlation_limit = "correlation_limit"
    daily_loss_limit = "daily_loss_limit"
    drawdown_limit = "drawdown_limit"
    rate_limit = "rate_limit"


class ScopeType(str, enum.Enum):
    """Scope for kill switches and circuit breakers."""
    global_scope = "global"
    portfolio = "portfolio"
    instrument = "instrument"
    market = "market"


class BreakerState(str, enum.Enum):
    """Lifecycle states of a circuit breaker."""
    armed = "armed"
    tripped = "tripped"
    half_open = "half_open"
