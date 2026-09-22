"""Signal Ranking Engine with configurable multi-factor scoring and feature normalization."""
import math
from collections.abc import Sequence
from datetime import UTC, datetime

from app.domains.portfolio.enums import RankingMethod
from app.domains.portfolio.schemas import PortfolioSnapshot, SignalRankingScore
from app.domains.strategies.schemas import TradingSignal


class SignalRankingEngine:
    """Ranks trading signals using multi-factor normalized scoring and explainable feature breakdowns."""

    def __init__(
        self,
        method: RankingMethod = RankingMethod.multi_factor_linear,
        weights: dict[str, float] | None = None,
        decay_half_life_seconds: float = 1800.0,  # 30-minute half life
    ):
        self.method = method
        self.weights = weights or {
            "confidence": 0.35,
            "risk_reward": 0.25,
            "freshness": 0.20,
            "historical_sharpe": 0.20,
        }
        self.decay_half_life_seconds = decay_half_life_seconds

        # Normalize weights so sum equals 1.0
        total_w = sum(self.weights.values())
        if total_w > 0:
            self.normalized_weights = {k: v / total_w for k, v in self.weights.items()}
        else:
            self.normalized_weights = {"confidence": 1.0}

    def rank_signals(
        self,
        signals: Sequence[TradingSignal],
        current_time: datetime,
        portfolio_snapshot: PortfolioSnapshot | None = None,
        strategy_sharpe_ratios: dict[str, float] | None = None,
    ) -> list[SignalRankingScore]:
        """Calculates multi-factor composite scores and ranks all signals in descending order."""
        if not signals:
            return []

        curr_ts = current_time if current_time.tzinfo else current_time.replace(tzinfo=UTC)
        strategy_sharpes = strategy_sharpe_ratios or {}

        scored_items: list[tuple[float, TradingSignal, dict[str, float]]] = []

        for sig in signals:
            features = self._calculate_features(sig, curr_ts, strategy_sharpes)
            
            if self.method == RankingMethod.equal_rank:
                score = 1.0
            elif self.method == RankingMethod.confidence_weighted:
                score = features["confidence"]
            elif self.method == RankingMethod.risk_reward_weighted:
                score = features["risk_reward"]
            elif self.method == RankingMethod.sharpe_weighted:
                score = features["historical_sharpe"]
            else:  # multi_factor_linear
                score = sum(
                    features.get(k, 0.0) * self.normalized_weights.get(k, 0.0)
                    for k in self.normalized_weights
                )
            
            # Bound composite score in [0.0, 1.0]
            bounded_score = max(0.0, min(1.0, float(score)))
            scored_items.append((bounded_score, sig, features))

        # Sort descending by composite score, then breaking ties by confidence, then timestamp
        scored_items.sort(
            key=lambda item: (
                item[0],
                item[1].confidence,
                item[1].timestamp.timestamp(),
            ),
            reverse=True,
        )

        ranked_results: list[SignalRankingScore] = []
        for rank_idx, (score, sig, features) in enumerate(scored_items, start=1):
            expl = (
                f"Rank {rank_idx}: Score {score:.4f} (Conf: {features['confidence']:.2f}, "
                f"R:R: {features['risk_reward']:.2f}, Fresh: {features['freshness']:.2f}, "
                f"Sharpe: {features['historical_sharpe']:.2f})"
            )
            ranked_results.append(
                SignalRankingScore(
                    signal_id=sig.signal_id,
                    instrument_id=sig.instrument_id,
                    symbol=sig.symbol,
                    strategy_id=sig.strategy_id,
                    direction=sig.direction,
                    composite_score=score,
                    rank=rank_idx,
                    feature_breakdown=features,
                    explanation=expl,
                )
            )

        return ranked_results

    def _calculate_features(
        self,
        sig: TradingSignal,
        current_time: datetime,
        strategy_sharpes: dict[str, float],
    ) -> dict[str, float]:
        """Extracts and normalizes features into [0.0, 1.0]."""
        # 1. Confidence [0, 1]
        f_conf = max(0.0, min(1.0, float(sig.confidence)))

        # 2. Risk-Reward Ratio (normalized: 1.0 maps to 0.33, 3.0 maps to 1.0)
        rr = float(sig.risk_reward_ratio) if sig.risk_reward_ratio is not None else 1.5
        f_rr = max(0.0, min(1.0, rr / 3.0))

        # 3. Freshness decay: e^(-lambda * delta_t)
        sig_ts = sig.timestamp if sig.timestamp.tzinfo else sig.timestamp.replace(tzinfo=UTC)
        delta_seconds = max(0.0, (current_time - sig_ts).total_seconds())
        decay_constant = math.log(2.0) / max(1.0, self.decay_half_life_seconds)
        f_fresh = math.exp(-decay_constant * delta_seconds)
        f_fresh = max(0.0, min(1.0, f_fresh))

        # 4. Historical Strategy Sharpe (normalized: 0.0 -> 0.0, 3.0+ -> 1.0)
        sharpe = strategy_sharpes.get(sig.strategy_id, 1.0)
        f_sharpe = max(0.0, min(1.0, sharpe / 3.0))

        return {
            "confidence": f_conf,
            "risk_reward": f_rr,
            "freshness": f_fresh,
            "historical_sharpe": f_sharpe,
        }
