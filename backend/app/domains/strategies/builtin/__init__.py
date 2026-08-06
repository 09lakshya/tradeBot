"""Automatic discovery and registration of all built-in institutional strategies."""
from app.domains.strategies.builtin.institutional.opening_range_breakout import OpeningRangeBreakoutStrategy
from app.domains.strategies.builtin.institutional.relative_strength import RelativeStrengthStrategy
from app.domains.strategies.builtin.mean_reversion.bollinger_bands import BollingerBandsStrategy
from app.domains.strategies.builtin.mean_reversion.vwap_reversion import VWAPReversionStrategy
from app.domains.strategies.builtin.mean_reversion.zscore import ZScoreMeanReversionStrategy
from app.domains.strategies.builtin.momentum.breakout import DonchianBreakoutStrategy
from app.domains.strategies.builtin.momentum.momentum_ranking import MomentumRankingStrategy
from app.domains.strategies.builtin.momentum.rsi_strategy import RSIStrategy
from app.domains.strategies.builtin.momentum.stochastic_strategy import StochasticStrategy
from app.domains.strategies.builtin.multi_factor.composite import MultiFactorCompositeStrategy
from app.domains.strategies.builtin.price_action.candlestick_patterns import CandlestickPatternStrategy
from app.domains.strategies.builtin.price_action.gap_trading import GapTradingStrategy
from app.domains.strategies.builtin.price_action.support_resistance import SupportResistancePivotStrategy
from app.domains.strategies.builtin.trend.adx_trend import ADXTrendStrategy
from app.domains.strategies.builtin.trend.ema_crossover import EMACrossoverStrategy
from app.domains.strategies.builtin.trend.macd_strategy import MACDTrendStrategy
from app.domains.strategies.builtin.trend.sma_crossover import SMACrossoverStrategy
from app.domains.strategies.builtin.volatility.atr_breakout import ATRBreakoutStrategy
from app.domains.strategies.builtin.volatility.keltner_channels import KeltnerChannelStrategy
from app.domains.strategies.builtin.volume.obv_strategy import OBVTrendStrategy
from app.domains.strategies.builtin.volume.volume_breakout import VolumeBreakoutStrategy

__all__ = [
    "EMACrossoverStrategy",
    "SMACrossoverStrategy",
    "MACDTrendStrategy",
    "ADXTrendStrategy",
    "RSIStrategy",
    "StochasticStrategy",
    "MomentumRankingStrategy",
    "DonchianBreakoutStrategy",
    "BollingerBandsStrategy",
    "VWAPReversionStrategy",
    "ZScoreMeanReversionStrategy",
    "ATRBreakoutStrategy",
    "KeltnerChannelStrategy",
    "OBVTrendStrategy",
    "VolumeBreakoutStrategy",
    "SupportResistancePivotStrategy",
    "GapTradingStrategy",
    "CandlestickPatternStrategy",
    "OpeningRangeBreakoutStrategy",
    "RelativeStrengthStrategy",
    "MultiFactorCompositeStrategy",
]
