"""On-Balance Volume (OBV) Trend Strategy."""
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
from app.domains.strategies.indicators import obv, sma
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class OBVTrendStrategy(BaseStrategy):
    """On-Balance Volume (OBV) Trend Confirmation & Signal Line Crossover Strategy."""

    strategy_id: str = "obv_trend"
    strategy_name: str = "On-Balance Volume Trend Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Enters on OBV moving average crossover to capture institutional volume accumulation."
    category: StrategyCategory = StrategyCategory.volume
    required_lookback: int = 35

    default_parameters: dict[str, Any] = {
        "obv_ma_period": 20,
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0200",
        "take_profit_pct": "0.0500",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        ma_p = int(self.params["obv_ma_period"])
        history = context.get_history(bar.instrument_id, lookback_bars=ma_p + 10)
        if len(history) < ma_p + 2:
            return []

        closes = [float(b.close) for b in history]
        volumes = [float(b.volume) for b in history]

        obv_vals = obv(closes, volumes)
        obv_ma = sma(obv_vals, ma_p)

        curr_obv, prev_obv = obv_vals[-1], obv_vals[-2]
        curr_ma, prev_ma = obv_ma[-1], obv_ma[-2]

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Bullish OBV Crossover: OBV crosses above its moving average
        if prev_obv <= prev_ma and curr_obv > curr_ma:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=0.82,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish,
                        supporting_indicators={
                            "obv": curr_obv,
                            "obv_ma": curr_ma,
                        },
                        explanation=f"Bullish Volume Accumulation: OBV ({curr_obv:.0f}) crossed above {ma_p}-period OBV SMA ({curr_ma:.0f}).",
                    )
                )

        # Bearish OBV Exit
        elif prev_obv >= prev_ma and curr_obv < curr_ma:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.80,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.trending_bearish,
                        supporting_indicators={
                            "obv": curr_obv,
                            "obv_ma": curr_ma,
                        },
                        explanation=f"Bearish Volume Distribution Exit: OBV ({curr_obv:.0f}) crossed below OBV SMA ({curr_ma:.0f}).",
                    )
                )

        return signals
