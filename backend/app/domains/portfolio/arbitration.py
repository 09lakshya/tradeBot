"""Signal Arbitration Engine for multi-signal conflict resolution and target blending."""
import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal

from app.domains.portfolio.enums import ArbitrationMethod
from app.domains.portfolio.schemas import ArbitrationDecision, SignalRankingScore
from app.domains.strategies.enums import SignalDirection
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.enums import OrderSide

log = logging.getLogger(__name__)


class SignalArbitrationEngine:
    """Resolves BUY vs SELL conflicts, blends multiple concordant signals, and eliminates duplicate emissions."""

    def __init__(
        self,
        method: ArbitrationMethod = ArbitrationMethod.net_confidence_weighted,
        neutral_threshold: float = 0.10,
    ):
        self.method = method
        self.neutral_threshold = neutral_threshold

    def arbitrate(
        self,
        instrument_id: uuid.UUID,
        signals: Sequence[TradingSignal],
        ranking_scores: dict[uuid.UUID, SignalRankingScore] | None = None,
    ) -> ArbitrationDecision:
        """Evaluates all signals for a single instrument and produces a deterministic ArbitrationDecision."""
        if not signals:
            raise ValueError(f"Cannot arbitrate empty signal set for instrument {instrument_id}")

        symbol = signals[0].symbol
        scores_map = ranking_scores or {}

        # Partition by direction (support long -> BUY, short -> SELL)
        buy_signals = [
            s for s in signals
            if s.direction in (SignalDirection.long, "buy", "long")
        ]
        sell_signals = [
            s for s in signals
            if s.direction in (SignalDirection.short, "sell", "short")
        ]

        # Case 1: No opposing conflicts (All BUY or All SELL)
        if not sell_signals and buy_signals:
            return self._blend_same_side(
                instrument_id, symbol, buy_signals, OrderSide.buy, scores_map, conflict_type="NO_CONFLICT"
            )
        elif not buy_signals and sell_signals:
            return self._blend_same_side(
                instrument_id, symbol, sell_signals, OrderSide.sell, scores_map, conflict_type="NO_CONFLICT"
            )

        # Case 2: BUY vs SELL Conflict
        if self.method == ArbitrationMethod.highest_ranking_wins:
            return self._arbitrate_highest_rank(instrument_id, symbol, signals, scores_map)
        else:  # net_confidence_weighted or consensus_blend
            return self._arbitrate_net_confidence(instrument_id, symbol, buy_signals, sell_signals, scores_map)

    def _arbitrate_net_confidence(
        self,
        instrument_id: uuid.UUID,
        symbol: str,
        buy_signals: list[TradingSignal],
        sell_signals: list[TradingSignal],
        scores_map: dict[uuid.UUID, SignalRankingScore],
    ) -> ArbitrationDecision:
        """Resolves opposing signals via net confidence differential."""
        total_buy_conf = sum(s.confidence for s in buy_signals)
        total_sell_conf = sum(s.confidence for s in sell_signals)
        net_diff = total_buy_conf - total_sell_conf

        if abs(net_diff) < self.neutral_threshold:
            # Conflict is balanced; neutralize position to protect capital
            return ArbitrationDecision(
                instrument_id=instrument_id,
                symbol=symbol,
                winning_side=None,
                selected_signals=[],
                discarded_signals=[s.signal_id for s in buy_signals + sell_signals],
                blended_confidence=0.0,
                blended_entry_price=None,
                blended_stop_loss=None,
                blended_take_profit=None,
                conflict_type="BUY_VS_SELL_BALANCED",
                resolution_method=self.method,
                reason=(
                    f"Opposing signals neutralized: Buy Conf ({total_buy_conf:.2f}) vs "
                    f"Sell Conf ({total_sell_conf:.2f}) within delta threshold {self.neutral_threshold:.2f}"
                ),
            )

        if net_diff > 0:
            winning_signals = buy_signals
            losing_signals = sell_signals
            winning_side = OrderSide.buy
        else:
            winning_signals = sell_signals
            losing_signals = buy_signals
            winning_side = OrderSide.sell

        # Blend targets from winning signals
        return self._blend_same_side(
            instrument_id=instrument_id,
            symbol=symbol,
            signals=winning_signals,
            side=winning_side,
            scores_map=scores_map,
            conflict_type="BUY_VS_SELL_RESOLVED",
            discarded_ids=[s.signal_id for s in losing_signals],
            override_reason=(
                f"Net confidence favored {winning_side.value.upper()}: "
                f"Buy Conf ({total_buy_conf:.2f}) vs Sell Conf ({total_sell_conf:.2f})"
            ),
        )

    def _arbitrate_highest_rank(
        self,
        instrument_id: uuid.UUID,
        symbol: str,
        signals: Sequence[TradingSignal],
        scores_map: dict[uuid.UUID, SignalRankingScore],
    ) -> ArbitrationDecision:
        """Highest ranking signal executes unconditionally."""
        best_sig = min(
            signals,
            key=lambda s: scores_map.get(s.signal_id).rank if s.signal_id in scores_map else 9999,
        )
        winning_side = OrderSide.buy if best_sig.direction in (SignalDirection.long, "buy", "long") else OrderSide.sell
        discarded = [s.signal_id for s in signals if s.signal_id != best_sig.signal_id]

        return ArbitrationDecision(
            instrument_id=instrument_id,
            symbol=symbol,
            winning_side=winning_side,
            selected_signals=[best_sig.signal_id],
            discarded_signals=discarded,
            blended_confidence=best_sig.confidence,
            blended_entry_price=best_sig.entry_price,
            blended_stop_loss=best_sig.stop_loss,
            blended_take_profit=best_sig.take_profit,
            conflict_type="BUY_VS_SELL_HIGHEST_RANK",
            resolution_method=ArbitrationMethod.highest_ranking_wins,
            reason=f"Selected highest-ranked strategy signal from {best_sig.strategy_id} (Score: {scores_map.get(best_sig.signal_id, 0.0)})",
        )

    def _blend_same_side(
        self,
        instrument_id: uuid.UUID,
        symbol: str,
        signals: list[TradingSignal],
        side: OrderSide,
        scores_map: dict[uuid.UUID, SignalRankingScore],
        conflict_type: str,
        discarded_ids: list[uuid.UUID] | None = None,
        override_reason: str | None = None,
    ) -> ArbitrationDecision:
        """Confidence-weighted consensus blending for same-side signals."""
        total_conf = sum(s.confidence for s in signals)
        if total_conf <= 0:
            total_conf = float(len(signals))

        # Blended confidence bounded in [0, 1]
        blended_conf = min(1.0, total_conf / max(1.0, float(len(signals))))

        # Weighted averages for price targets
        valid_entries = [s for s in signals if s.entry_price is not None]
        if valid_entries:
            blended_entry = sum(s.entry_price * Decimal(str(s.confidence)) for s in valid_entries) / sum(
                Decimal(str(s.confidence)) for s in valid_entries
            )
        else:
            blended_entry = None

        valid_sl = [s for s in signals if s.stop_loss is not None]
        if valid_sl:
            blended_sl = sum(s.stop_loss * Decimal(str(s.confidence)) for s in valid_sl) / sum(
                Decimal(str(s.confidence)) for s in valid_sl
            )
        else:
            blended_sl = None

        valid_tp = [s for s in signals if s.take_profit is not None]
        if valid_tp:
            blended_tp = sum(s.take_profit * Decimal(str(s.confidence)) for s in valid_tp) / sum(
                Decimal(str(s.confidence)) for s in valid_tp
            )
        else:
            blended_tp = None

        strategies_str = ", ".join(set(s.strategy_id for s in signals))
        reason = override_reason or (
            f"Consensus {side.value.upper()} signal blended from {len(signals)} sources ({strategies_str})"
        )

        return ArbitrationDecision(
            instrument_id=instrument_id,
            symbol=symbol,
            winning_side=side,
            selected_signals=[s.signal_id for s in signals],
            discarded_signals=discarded_ids or [],
            blended_confidence=blended_conf,
            blended_entry_price=blended_entry,
            blended_stop_loss=blended_sl,
            blended_take_profit=blended_tp,
            conflict_type=conflict_type,
            resolution_method=self.method,
            reason=reason,
        )
