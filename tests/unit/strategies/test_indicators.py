"""Comprehensive mathematical validation tests for the indicator library."""
import math
import pytest

from app.domains.strategies.indicators import (
    adx,
    atr,
    bollinger_bands,
    candlestick_patterns,
    donchian_channels,
    ema,
    keltner_channels,
    macd,
    obv,
    pivot_points_standard,
    roc,
    rsi,
    sma,
    stochastic,
    vwap,
)


class TestIndicatorCalculations:
    """Mathematical validation for vectorized pure indicators."""

    def test_sma_calculation(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        res = sma(prices, 3)
        assert len(res) == 5
        assert math.isnan(res[0])
        assert math.isnan(res[1])
        assert res[2] == pytest.approx(20.0)
        assert res[3] == pytest.approx(30.0)
        assert res[4] == pytest.approx(40.0)

    def test_ema_calculation(self):
        prices = [10.0, 10.0, 10.0, 20.0, 20.0]
        res = ema(prices, 3)
        assert len(res) == 5
        assert math.isnan(res[0])
        assert math.isnan(res[1])
        assert res[2] == 10.0
        assert res[3] == 15.0
        assert res[4] == 17.5

    def test_rsi_calculation(self):
        # Monotonically increasing prices -> RSI should approach 100
        up_prices = [10.0 + i for i in range(30)]
        up_rsi = rsi(up_prices, 14)
        assert up_rsi[-1] == pytest.approx(100.0, abs=1e-2)

        # Monotonically decreasing prices -> RSI should approach 0
        down_prices = [100.0 - i for i in range(30)]
        down_rsi = rsi(down_prices, 14)
        assert down_rsi[-1] == pytest.approx(0.0, abs=1e-2)

    def test_macd_calculation(self):
        prices = [100.0 + i * 0.5 for i in range(40)]
        macd_line, sig_line, hist = macd(prices, fast_period=12, slow_period=26, signal_period=9)
        assert len(macd_line) == 40
        assert len(sig_line) == 40
        assert len(hist) == 40
        assert macd_line[-1] > 0  # Uptrend produces positive MACD

    def test_bollinger_bands(self):
        prices = [100.0 for _ in range(25)]
        upper, middle, lower, pct_b, bandwidth = bollinger_bands(prices, period=20, num_std=2.0)
        assert middle[-1] == 100.0
        assert upper[-1] == 100.0
        assert lower[-1] == 100.0
        assert pct_b[-1] == 0.5

        # With volatility
        volatile_prices = [100.0 + (5.0 if i % 2 == 0 else -5.0) for i in range(25)]
        upper_v, middle_v, lower_v, pct_b_v, bw_v = bollinger_bands(volatile_prices, period=20, num_std=2.0)
        assert upper_v[-1] > middle_v[-1] > lower_v[-1]
        assert bw_v[-1] > 0

    def test_atr_calculation(self):
        highs = [105.0] * 20
        lows = [95.0] * 20
        closes = [100.0] * 20
        atr_vals = atr(highs, lows, closes, 14)
        assert len(atr_vals) == 20
        assert atr_vals[-1] == pytest.approx(10.0, abs=1e-2)

    def test_stochastic_oscillator(self):
        highs = [10.0 + i for i in range(25)]
        lows = [5.0 + i for i in range(25)]
        closes = [9.0 + i for i in range(25)]
        k_line, d_line = stochastic(highs, lows, closes, k_period=14, d_period=3)
        assert len(k_line) == 25
        assert len(d_line) == 25
        assert 0.0 <= k_line[-1] <= 100.0
        assert 0.0 <= d_line[-1] <= 100.0

    def test_obv_calculation(self):
        closes = [10.0, 12.0, 11.0, 15.0]
        volumes = [100.0, 200.0, 150.0, 300.0]
        obv_vals = obv(closes, volumes)
        assert obv_vals[0] == 100.0
        assert obv_vals[1] == 300.0  # Up bar (+200)
        assert obv_vals[2] == 150.0  # Down bar (-150)
        assert obv_vals[3] == 450.0  # Up bar (+300)

    def test_roc_calculation(self):
        prices = [100.0, 102.0, 105.0, 110.0]
        roc_vals = roc(prices, 3)
        assert roc_vals[-1] == pytest.approx(10.0)  # (110 - 100) / 100 * 100 = 10%

    def test_donchian_channels(self):
        highs = [10.0, 12.0, 15.0, 14.0, 16.0]
        lows = [8.0, 9.0, 11.0, 10.0, 12.0]
        upper, middle, lower = donchian_channels(highs, lows, 3)
        assert upper[-1] == 16.0
        assert lower[-1] == 10.0
        assert middle[-1] == 13.0

    def test_vwap_calculation(self):
        highs = [105.0, 110.0]
        lows = [95.0, 100.0]
        closes = [100.0, 105.0]
        volumes = [1000.0, 2000.0]
        vwap_vals = vwap(highs, lows, closes, volumes)
        # Bar 1: tp=100, vol=1000 -> vwap=100
        assert vwap_vals[0] == 100.0
        # Bar 2: tp=105, vol=2000 -> cum_tp_v=100k + 210k = 310k, cum_v=3000 -> 310/3 = 103.33
        assert vwap_vals[1] == pytest.approx(103.3333, abs=1e-3)

    def test_pivot_points(self):
        pivots = pivot_points_standard(110.0, 90.0, 100.0)
        assert pivots["P"] == 100.0
        assert pivots["R1"] == 110.0
        assert pivots["S1"] == 90.0
        assert pivots["R2"] == 120.0
        assert pivots["S2"] == 80.0

    def test_candlestick_patterns(self):
        # Hammer: small real body at top, long lower shadow
        opens = [100.0, 100.0]
        highs = [102.0, 100.2]
        lows = [98.0, 90.0]
        closes = [99.0, 100.2]
        patterns = candlestick_patterns(opens, highs, lows, closes)
        assert patterns["hammer"][-1] is True
