"""Pluggable Portfolio Allocation Policies."""
import abc
from decimal import Decimal
from typing import Sequence
import uuid

from app.domains.portfolio.enums import AllocationPolicyType
from app.domains.portfolio.schemas import ArbitrationDecision, PortfolioSnapshot, SignalRankingScore


class BaseAllocationPolicy(abc.ABC):
    """Abstract interface for portfolio allocation policies."""

    @property
    @abc.abstractmethod
    def policy_type(self) -> AllocationPolicyType:
        """Returns policy enum type."""
        pass

    @abc.abstractmethod
    def compute_target_weights(
        self,
        approved_decisions: Sequence[ArbitrationDecision],
        portfolio_snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        total_allocation_budget: Decimal,
    ) -> dict[uuid.UUID, Decimal]:
        """Calculates unconstrained target portfolio weights summing up to total_allocation_budget."""
        pass


class EqualWeightPolicy(BaseAllocationPolicy):
    """Allocates equal weight across all selected candidate assets."""

    @property
    def policy_type(self) -> AllocationPolicyType:
        return AllocationPolicyType.equal_weight

    def compute_target_weights(
        self,
        approved_decisions: Sequence[ArbitrationDecision],
        portfolio_snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        total_allocation_budget: Decimal,
    ) -> dict[uuid.UUID, Decimal]:
        n = len(approved_decisions)
        if n == 0:
            return {}
        weight_per_asset = (total_allocation_budget / Decimal(str(n))).quantize(Decimal("0.0001"))
        return {d.instrument_id: weight_per_asset for d in approved_decisions}


class VolatilityInversePolicy(BaseAllocationPolicy):
    """Allocates weights inversely proportional to rolling historical asset volatility."""

    @property
    def policy_type(self) -> AllocationPolicyType:
        return AllocationPolicyType.volatility_inverse

    def compute_target_weights(
        self,
        approved_decisions: Sequence[ArbitrationDecision],
        portfolio_snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        total_allocation_budget: Decimal,
    ) -> dict[uuid.UUID, Decimal]:
        if not approved_decisions:
            return {}

        inv_vols: dict[uuid.UUID, Decimal] = {}
        for d in approved_decisions:
            vol = portfolio_snapshot.volatilities.get(d.instrument_id, Decimal("0.2000"))
            vol_safe = max(Decimal("0.0100"), vol)
            inv_vols[d.instrument_id] = Decimal("1.0000") / vol_safe

        sum_inv = sum(inv_vols.values())
        if sum_inv <= 0:
            return EqualWeightPolicy().compute_target_weights(
                approved_decisions, portfolio_snapshot, ranking_scores, total_allocation_budget
            )

        return {
            inst_id: (val / sum_inv * total_allocation_budget).quantize(Decimal("0.0001"))
            for inst_id, val in inv_vols.items()
        }


class ScoreProportionalPolicy(BaseAllocationPolicy):
    """Allocates weights proportionally to multi-factor signal ranking scores."""

    @property
    def policy_type(self) -> AllocationPolicyType:
        return AllocationPolicyType.score_proportional

    def compute_target_weights(
        self,
        approved_decisions: Sequence[ArbitrationDecision],
        portfolio_snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        total_allocation_budget: Decimal,
    ) -> dict[uuid.UUID, Decimal]:
        if not approved_decisions:
            return {}

        scores: dict[uuid.UUID, Decimal] = {}
        for d in approved_decisions:
            # Average score among selected signals for this decision
            selected_scores = [
                ranking_scores[sig_id].composite_score
                for sig_id in d.selected_signals
                if sig_id in ranking_scores
            ]
            avg_score = sum(selected_scores) / len(selected_scores) if selected_scores else 0.5
            scores[d.instrument_id] = Decimal(str(round(avg_score, 4)))

        total_score = sum(scores.values())
        if total_score <= 0:
            return EqualWeightPolicy().compute_target_weights(
                approved_decisions, portfolio_snapshot, ranking_scores, total_allocation_budget
            )

        return {
            inst_id: (sc / total_score * total_allocation_budget).quantize(Decimal("0.0001"))
            for inst_id, sc in scores.items()
        }


class RiskParityPolicy(BaseAllocationPolicy):
    """Approximates Equal Risk Contribution (Risk Parity) under diagonal/uncorrelated assumption."""

    @property
    def policy_type(self) -> AllocationPolicyType:
        return AllocationPolicyType.risk_parity

    def compute_target_weights(
        self,
        approved_decisions: Sequence[ArbitrationDecision],
        portfolio_snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        total_allocation_budget: Decimal,
    ) -> dict[uuid.UUID, Decimal]:
        # Under independent risk assumption, ERC weight is inversely proportional to standard deviation
        return VolatilityInversePolicy().compute_target_weights(
            approved_decisions, portfolio_snapshot, ranking_scores, total_allocation_budget
        )


class AllocationPolicyRegistry:
    """Factory registry for looking up and instantiating allocation policies."""

    _policies: dict[AllocationPolicyType, type[BaseAllocationPolicy]] = {
        AllocationPolicyType.equal_weight: EqualWeightPolicy,
        AllocationPolicyType.volatility_inverse: VolatilityInversePolicy,
        AllocationPolicyType.score_proportional: ScoreProportionalPolicy,
        AllocationPolicyType.risk_parity: RiskParityPolicy,
    }

    @classmethod
    def get(cls, policy_type: AllocationPolicyType) -> BaseAllocationPolicy:
        policy_cls = cls._policies.get(policy_type)
        if not policy_cls:
            return ScoreProportionalPolicy()
        return policy_cls()
