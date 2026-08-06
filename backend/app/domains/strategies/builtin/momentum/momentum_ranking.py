"""Momentum Ranking and Rate of Change (ROC) Strategy."""
from decimal import Decimal
from typing import Any

from app.domains.backtest.data_feed import HistoricalBar
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.enums import (
    MarketRegime,
    SignalDirection,
    SignalType,
    StrategyCategory,
)
from app.domains.strategies.indicators import roc, sma
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class MomentumRankingStrategy(BaseStrategy):
    """Rate-of-Change (ROC) Momentum Ranking and Acceleration Strategy."""

    strategy_id: str = "momentum_ranking"
    strategy_name: str = "ROC Momentum Acceleration Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Measures rate-of-change velocity and moving average acceleration for momentum entry."
    category: StrategyCategory = StrategyCategory.momentum
    required_lookback: int = 50

    default_parameters: dict[str, Any] = {
        "roc_period": 20,
        "roc_threshold": 3.0,  # 3% price change threshold
        "ma_filter_period": 50,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0250",
        "take_profit_pct": "0.0600",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        ma_p = int(self.params["ma_filter_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=ma_p + 10)
        if len(history) < ma_p:
            return []

        closes = [float(b.close) for b in history]
        roc_p = int(self.params["roc_period"])
        roc_vals = roc(closes, roc_p)
        ma_vals = sma(closes, ma_p)

        curr_roc, prev_roc = roc_vals[-1], roc_vals[-2]
        curr_ma = ma_vals[-1]
        roc_thresh = float(self.params["roc_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Momentum Acceleration: ROC crosses above threshold AND price is above 50 SMA
        if prev_roc <= roc_thresh and curr_roc > roc_thresh and closes[-1] > curr_ma:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=min(1.0, 0.75 + (curr_roc / 20.0) * 0.25),
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "roc": curr_roc,
                            "prev_roc": prev_roc,
                            "roc_threshold": roc_thresh,
                            "filter_sma": curr_ma,
                        },
                        explanation=f"Momentum Acceleration: ROC ({curr_roc:.2f}%) surged above threshold ({roc_thresh:.2f}%) above 50 SMA ({curr_ma:.2f}).",
                    )
                )

        # Momentum Decay Exit: ROC drops below 0
        elif curr_roc < 0.0:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.75,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "roc": curr_roc,
                        },
                        explanation=f"Momentum Decay Exit: ROC turned negative ({curr_roc:.2f}%).",
                    )
                )

        return signals
