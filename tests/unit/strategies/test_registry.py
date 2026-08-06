"""Unit tests for Strategy Registry, Discovery, and Versioning."""
import pytest

from app.domains.strategies.base import BaseStrategy
from app.domains.strategies.exceptions import (
    StrategyNotFoundError,
    StrategyVersionMismatchError,
)
from app.domains.strategies.registry import StrategyRegistry
import app.domains.strategies.builtin  # Load all 21 strategies


class TestStrategyRegistry:
    """Strategy discovery, schema inspection, and lifecycle validation."""

    def test_registry_contains_all_strategies(self):
        strategies = StrategyRegistry.list_strategies()
        assert len(strategies) >= 21
        strat_ids = {s.strategy_id for s in strategies}

        expected_ids = {
            "ema_crossover",
            "sma_crossover",
            "macd_trend",
            "adx_trend",
            "rsi_momentum",
            "stochastic_momentum",
            "momentum_ranking",
            "donchian_breakout",
            "bollinger_mean_reversion",
            "vwap_reversion",
            "zscore_reversion",
            "atr_breakout",
            "keltner_channel",
            "obv_trend",
            "volume_breakout",
            "support_resistance",
            "gap_trading",
            "candlestick_patterns",
            "opening_range_breakout",
            "relative_strength",
            "multi_factor_composite",
        }

        assert expected_ids.issubset(strat_ids)

    def test_get_strategy_metadata(self):
        meta = StrategyRegistry.get_metadata("ema_crossover")
        assert meta.strategy_id == "ema_crossover"
        assert meta.name == "EMA Crossover Trend Strategy"
        assert meta.version == "1.0.0"
        assert "fast_period" in meta.default_parameters

    def test_instantiate_strategy(self):
        instance = StrategyRegistry.create_instance("rsi_momentum", params={"oversold_threshold": 25.0})
        assert instance.strategy_id == "rsi_momentum"
        assert instance.params["oversold_threshold"] == 25.0

    def test_strategy_not_found(self):
        with pytest.raises(StrategyNotFoundError):
            StrategyRegistry.get_strategy_class("non_existent_strategy_id")

    def test_version_mismatch(self):
        with pytest.raises(StrategyVersionMismatchError):
            StrategyRegistry.get_strategy_class("ema_crossover", version="99.9.9")
