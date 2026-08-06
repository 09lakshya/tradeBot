"""Mansfield Relative Strength Strategy."""
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
class RelativeStrengthStrategy(BaseStrategy):
    """Institutional Relative Strength & Outperformance Strategy."""

    strategy_id: str = "relative_strength"
    strategy_name: str = "Relative Strength (RS) Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Buys assets exhibiting strong relative strength and sustained price momentum above 50 SMA."
    category: StrategyCategory = StrategyCategory.institutional
    required_lookback: int = 55

    default_parameters: dict[str, Any] = {
        "rs_period": 20,
        "rs_threshold": 4.0,  # 4% RS momentum
        "trend_filter_period": 50,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0250",
        "take_profit_pct": "0.0600",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        filter_p = int(self.params["trend_filter_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=filter_p + 10)
        if len(history) < filter_p:
            return []

        closes = [float(b.close) for b in history]
        rs_p = int(self.params["rs_period"])
        rs_vals = roc(closes, rs_p)
        trend_vals = sma(closes, filter_p)

        curr_rs, prev_rs = rs_vals[-1], rs_vals[-2]
        curr_trend = trend_vals[-1]
        thresh = float(self.params["rs_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Outperformance Entry: RS surges above threshold AND Price > 50 SMA
        if prev_rs <= thresh and curr_rs > thresh and closes[-1] > curr_trend:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=min(1.0, 0.80 + (curr_rs / 20.0) * 0.20),
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "rs_roc": curr_rs,
                            "trend_sma": curr_trend,
                            "rs_threshold": thresh,
                        },
                        explanation=f"Institutional Relative Strength: RS ({curr_rs:.2f}%) accelerated above {thresh:.1f}% threshold above 50 SMA ({curr_trend:.2f}).",
                    )
                )

        # Underperformance Exit: RS drops below 0
        elif curr_rs < 0.0:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.80,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "rs_roc": curr_rs,
                        },
                        explanation=f"Relative Strength Exit: Relative momentum weakened into negative territory ({curr_rs:.2f}%).",
                    )
                )

        return signals
