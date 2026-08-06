"""Multi-Factor Composite Scoring Strategy."""
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
from app.domains.strategies.indicators import ema, macd, rsi, sma
from app.domains.strategies.registry import register_strategy
from app.domains.strategies.schemas import TradingSignal


@register_strategy
class MultiFactorCompositeStrategy(BaseStrategy):
    """Multi-Factor Composite Model combining Trend (40%), Momentum (30%), and Volume (30%)."""

    strategy_id: str = "multi_factor_composite"
    strategy_name: str = "Multi-Factor Composite Alpha Strategy"
    version: str = "1.0.0"
    author: str = "Quantitative Research Team"
    description: str = "Synthesizes multi-factor weights (Trend, RSI Momentum, and Volume accumulation) into a composite confidence score."
    category: StrategyCategory = StrategyCategory.multi_factor
    required_lookback: int = 60

    default_parameters: dict[str, Any] = {
        "trend_weight": 0.40,
        "momentum_weight": 0.30,
        "volume_weight": 0.30,
        "composite_entry_threshold": 0.70,  # 70% composite score
        "composite_exit_threshold": 0.35,  # 35% composite score
        "trade_qty": "10.0000",
        "stop_loss_pct": "0.0250",
        "take_profit_pct": "0.0550",
    }

    def on_bar(self, bar: HistoricalBar, context: StrategyContext) -> list[TradingSignal]:
        history = context.get_history(bar.instrument_id, lookback_bars=60)
        if len(history) < 50:
            return []

        closes = [float(b.close) for b in history]
        volumes = [float(b.volume) for b in history]

        # 1. Trend Factor (EMA 20 > EMA 50)
        ema20 = ema(closes, 20)[-1]
        ema50 = ema(closes, 50)[-1]
        trend_score = 1.0 if (closes[-1] > ema20 > ema50) else (0.5 if (closes[-1] > ema50) else 0.0)

        # 2. Momentum Factor (RSI 14 between 45 and 65, healthy bullish expansion)
        rsi_vals = rsi(closes, 14)
        curr_rsi = rsi_vals[-1]
        if 50.0 <= curr_rsi <= 70.0:
            momentum_score = 1.0
        elif 40.0 <= curr_rsi < 50.0:
            momentum_score = 0.6
        elif curr_rsi > 70.0:
            momentum_score = 0.4  # Slightly extended
        else:
            momentum_score = 0.1

        # 3. Volume Factor (Volume > 20-period Avg Volume on green candle)
        vol_sma = sma(volumes, 20)[-1]
        curr_vol = volumes[-1]
        is_green = float(bar.close) >= float(bar.open)
        if curr_vol > vol_sma and is_green:
            volume_score = 1.0
        elif is_green:
            volume_score = 0.5
        else:
            volume_score = 0.0

        # Composite Score Calculation
        w_trend = float(self.params["trend_weight"])
        w_mom = float(self.params["momentum_weight"])
        w_vol = float(self.params["volume_weight"])

        composite_score = (
            w_trend * trend_score +
            w_mom * momentum_score +
            w_vol * volume_score
        )

        entry_thresh = float(self.params["composite_entry_threshold"])
        exit_thresh = float(self.params["composite_exit_threshold"])

        curr_pos = context.get_current_position(bar.instrument_id)
        signals = []
        trade_qty = Decimal(str(self.params["trade_qty"]))
        sl_pct = Decimal(str(self.params["stop_loss_pct"]))
        tp_pct = Decimal(str(self.params["take_profit_pct"]))

        # Composite Entry
        if composite_score >= entry_thresh:
            if curr_pos <= Decimal("0.0000"):
                sl = (bar.close * (Decimal("1.0") - sl_pct)).quantize(Decimal("0.01"))
                tp = (bar.close * (Decimal("1.0") + tp_pct)).quantize(Decimal("0.01"))
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.entry_long,
                        direction=SignalDirection.long,
                        confidence=composite_score,
                        target_quantity=trade_qty,
                        entry_price=bar.close,
                        stop_loss=sl,
                        take_profit=tp,
                        market_regime=MarketRegime.trending_bullish if trend_score == 1.0 else MarketRegime.ranging,
                        supporting_indicators={
                            "composite_score": composite_score,
                            "trend_score": trend_score,
                            "momentum_score": momentum_score,
                            "volume_score": volume_score,
                            "rsi": curr_rsi,
                            "ema20": ema20,
                            "ema50": ema50,
                        },
                        explanation=f"Multi-Factor Confluence: Composite score ({composite_score*100:.1f}%) met entry threshold ({entry_thresh*100:.0f}%). Trend={trend_score:.1f}, Mom={momentum_score:.1f}, Vol={volume_score:.1f}.",
                    )
                )

        # Composite Exit
        elif composite_score <= exit_thresh:
            if curr_pos > Decimal("0.0000"):
                signals.append(
                    self.create_signal(
                        bar=bar,
                        signal_type=SignalType.exit_long,
                        direction=SignalDirection.flat,
                        confidence=0.85,
                        target_quantity=curr_pos,
                        entry_price=bar.close,
                        market_regime=MarketRegime.ranging,
                        supporting_indicators={
                            "composite_score": composite_score,
                        },
                        explanation=f"Multi-Factor Score Decay: Composite score ({composite_score*100:.1f}%) fell below exit threshold ({exit_thresh*100:.0f}%).",
                    )
                )

        return signals
