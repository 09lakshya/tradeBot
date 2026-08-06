"""Domain Enums for Portfolio Construction & Signal Arbitration Engine."""
from enum import Enum


class RankingMethod(str, Enum):
    """Supported signal ranking algorithms."""
    multi_factor_linear = "multi_factor_linear"
    confidence_weighted = "confidence_weighted"
    sharpe_weighted = "sharpe_weighted"
    risk_reward_weighted = "risk_reward_weighted"
    equal_rank = "equal_rank"


class ArbitrationMethod(str, Enum):
    """Methods for resolving conflicting or duplicate signals for the same instrument."""
    net_confidence_weighted = "net_confidence_weighted"
    highest_ranking_wins = "highest_ranking_wins"
    consensus_blend = "consensus_blend"
    first_in_time = "first_in_time"


class AllocationPolicyType(str, Enum):
    """Portfolio capital allocation strategies."""
    equal_weight = "equal_weight"
    volatility_inverse = "volatility_inverse"
    risk_parity = "risk_parity"
    expected_return_weighted = "expected_return_weighted"
    score_proportional = "score_proportional"
    maximum_diversification = "maximum_diversification"


class SizingMethod(str, Enum):
    """Position sizing formulas."""
    fixed_fractional = "fixed_fractional"
    volatility_adjusted = "volatility_adjusted"
    atr_risk_per_trade = "atr_risk_per_trade"
    half_kelly = "half_kelly"
    full_kelly = "full_kelly"


class OptimizationObjective(str, Enum):
    """Multi-objective optimization targets."""
    maximize_sharpe = "maximize_sharpe"
    minimize_volatility = "minimize_volatility"
    maximize_expected_return = "maximize_expected_return"
    risk_parity_target = "risk_parity_target"
    maximum_diversification = "maximum_diversification"


class CandidateOrderStatus(str, Enum):
    """Lifecycle status of a generated candidate order."""
    generated = "generated"
    forwarded_to_risk = "forwarded_to_risk"
    approved_by_risk = "approved_by_risk"
    rejected_by_risk = "rejected_by_risk"
    cancelled = "cancelled"
