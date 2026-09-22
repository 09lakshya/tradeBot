"""Stateless, deterministic portfolio optimization under multi-dimensional exposure and turnover constraints."""
import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal

from app.domains.portfolio.policies import AllocationPolicyRegistry
from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    PortfolioConstructionConfig,
    PortfolioSnapshot,
    SignalRankingScore,
)

log = logging.getLogger(__name__)


class PortfolioOptimizer:
    """Applies constrained optimization across instruments, sectors, and cash buffers."""

    def optimize(
        self,
        decisions: Sequence[ArbitrationDecision],
        snapshot: PortfolioSnapshot,
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        config: PortfolioConstructionConfig,
        instrument_sectors: dict[uuid.UUID, str] | None = None,
    ) -> tuple[dict[uuid.UUID, Decimal], dict[str, str]]:
        """Calculates final constrained portfolio target weights and attribution explanations."""
        # 1. Filter out neutralized decisions (winning_side is None)
        actionable = [d for d in decisions if d.winning_side is not None]
        if not actionable:
            return {}, {}

        sectors_map = instrument_sectors or {}

        # 2. Limit to top max_positions based on ranking scores
        sorted_actionable = self._sort_by_rank(actionable, ranking_scores)
        selected_candidates = sorted_actionable[: config.max_positions]

        # 3. Calculate total capital budget (1.0 - reserve_cash_pct) bounded by max_portfolio_exposure
        effective_budget = min(
            config.max_portfolio_exposure,
            Decimal("1.0000") - config.reserve_cash_pct,
        )
        if effective_budget <= 0:
            return {}, {"global": f"Zero allocation budget after reserving {config.reserve_cash_pct * 100}% cash"}

        # 4. Generate unconstrained weights from allocation policy
        policy = AllocationPolicyRegistry.get(config.allocation_policy)
        raw_weights = policy.compute_target_weights(
            approved_decisions=selected_candidates,
            portfolio_snapshot=snapshot,
            ranking_scores=ranking_scores,
            total_allocation_budget=effective_budget,
        )

        # 5. Apply Single Instrument Cap & Sector Caps iteratively
        constrained_weights: dict[uuid.UUID, Decimal] = {}
        sector_usage: dict[str, Decimal] = {}
        explanations: dict[str, str] = {}

        for decision in selected_candidates:
            inst_id = decision.instrument_id
            target_w = raw_weights.get(inst_id, Decimal("0.0000"))

            # Apply single instrument cap
            if target_w > config.max_instrument_weight:
                target_w = config.max_instrument_weight
                explanations[str(inst_id)] = (
                    f"Capped at max instrument limit {config.max_instrument_weight * 100}%"
                )

            # Apply sector cap
            sector = sectors_map.get(inst_id, snapshot.positions.get(inst_id, None) and snapshot.positions[inst_id].sector or "General")
            current_sec_w = sector_usage.get(sector, Decimal("0.0000"))
            if current_sec_w + target_w > config.max_sector_weight:
                allowed_w = max(Decimal("0.0000"), config.max_sector_weight - current_sec_w)
                target_w = allowed_w
                explanations[str(inst_id)] = (
                    f"Capped at remaining sector budget ({sector}: {allowed_w * 100:.2f}%)"
                )

            # 6. Apply Rebalancing Deadband check against current holding
            curr_pos_w = snapshot.current_weights.get(inst_id, Decimal("0.0000"))
            delta_w = abs(target_w - curr_pos_w)

            if delta_w < config.rebalance_deadband_pct and curr_pos_w > 0:
                # Inside deadband; suppress rebalance trade
                explanations[str(inst_id)] = (
                    f"Turnover deadband active: delta {delta_w * 100:.2f}% < threshold {config.rebalance_deadband_pct * 100:.2f}%"
                )
                continue

            if target_w > 0:
                constrained_weights[inst_id] = target_w.quantize(Decimal("0.0001"))
                sector_usage[sector] = current_sec_w + target_w
                if str(inst_id) not in explanations:
                    explanations[str(inst_id)] = (
                        f"Allocated {target_w * 100:.2f}% under {config.allocation_policy.value} policy"
                    )

        return constrained_weights, explanations

    def _sort_by_rank(
        self,
        decisions: list[ArbitrationDecision],
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
    ) -> list[ArbitrationDecision]:
        """Sorts decisions by best ranking score."""
        def get_best_score(decision: ArbitrationDecision) -> float:
            scores = [
                ranking_scores[sig_id].composite_score
                for sig_id in decision.selected_signals
                if sig_id in ranking_scores
            ]
            return max(scores) if scores else 0.0

        return sorted(decisions, key=get_best_score, reverse=True)
