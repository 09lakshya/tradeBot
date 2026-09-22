"""Strategy Composition and Pipeline Filtering Framework."""
from collections.abc import Callable
from typing import Any

from app.domains.backtest.data_feed import HistoricalBar
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.enums import StrategyCategory
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class ComposedStrategyPipeline(BaseStrategy):
    """Dynamically chains a signal-generating strategy through one or more independent filter strategies."""

    strategy_id: str = "composed_pipeline"
    strategy_name: str = "Composed Strategy Pipeline"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Chains primary signal generation with secondary trend, volatility, or volume filters."
    category: StrategyCategory = StrategyCategory.composite
    required_lookback: int = 100

    def __init__(
        self,
        params: dict[str, Any] | None = None,
        primary_strategy: BaseStrategy | None = None,
        filters: list[Callable[[HistoricalBar, StrategyContext, TradingSignal], bool]] | None = None,
    ):
        super().__init__(params)
        self.primary_strategy = primary_strategy
        self.filters = filters or []

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        if not self.primary_strategy:
            return []

        raw_signals = self.primary_strategy.on_bar(bar, context)
        filtered_signals = []

        for sig in raw_signals:
            passed_all_filters = True
            for filt in self.filters:
                if not filt(bar, context, sig):
                    passed_all_filters = False
                    break

            if passed_all_filters:
                # Augment explanation with composite filter confirmation
                updated_explanation = f"{sig.human_readable_explanation} [Passed {len(self.filters)} Composite Filters]"
                augmented_sig = self.create_signal(
                    bar=bar,
                    signal_type=sig.signal_type,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    target_quantity=sig.target_quantity,
                    entry_price=sig.entry_price,
                    stop_loss=sig.stop_loss,
                    take_profit=sig.take_profit,
                    expected_holding_period=sig.expected_holding_period,
                    market_regime=sig.market_regime,
                    supporting_indicators={
                        **sig.supporting_indicators,
                        "composite_filters_passed": len(self.filters),
                    },
                    explanation=updated_explanation,
                    metadata=sig.metadata,
                )
                filtered_signals.append(augmented_sig)

        return filtered_signals
