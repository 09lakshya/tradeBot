"""Deterministic, High-Performance Technical Indicator Library.

All functions are pure, numerically stable, vectorized where appropriate,
and have zero external runtime framework dependencies.
"""
import math
from typing import Sequence


# ============================================================================
# 1. Moving Averages
# ============================================================================

def sma(prices: Sequence[float], period: int) -> list[float]:
    """Simple Moving Average (SMA)."""
    n = len(prices)
    if period <= 0 or n < period:
        return [float("nan")] * n

    result = [float("nan")] * (period - 1)
    window_sum = sum(prices[:period])
    result.append(window_sum / period)

    for i in range(period, n):
        window_sum += prices[i] - prices[i - period]
        result.append(window_sum / period)

    return result


def ema(prices: Sequence[float], period: int, smoothing: float = 2.0) -> list[float]:
    """Exponential Moving Average (EMA)."""
    n = len(prices)
    if period <= 0 or n < period:
        return [float("nan")] * n

    result = [float("nan")] * (period - 1)
    # First EMA value is SMA of first 'period' elements
    current_ema = sum(prices[:period]) / period
    result.append(current_ema)

    multiplier = smoothing / (period + 1.0)

    for i in range(period, n):
        current_ema = (prices[i] - current_ema) * multiplier + current_ema
        result.append(current_ema)

    return result


def wma(prices: Sequence[float], period: int) -> list[float]:
    """Weighted Moving Average (WMA)."""
    n = len(prices)
    if period <= 0 or n < period:
        return [float("nan")] * n

    denominator = (period * (period + 1)) / 2.0
    result = [float("nan")] * (period - 1)

    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        weighted_sum = sum(w * val for w, val in enumerate(window, start=1))
        result.append(weighted_sum / denominator)

    return result


def dema(prices: Sequence[float], period: int) -> list[float]:
    """Double Exponential Moving Average (DEMA): 2*EMA - EMA(EMA)."""
    ema1 = ema(prices, period)
    valid_idx = period - 1
    ema2_raw = ema(ema1[valid_idx:], period)
    ema2 = [float("nan")] * (valid_idx + period - 1) + ema2_raw[period - 1:]

    n = len(prices)
    result = []
    for i in range(n):
        if math.isnan(ema1[i]) or math.isnan(ema2[i]):
            result.append(float("nan"))
        else:
            result.append(2.0 * ema1[i] - ema2[i])
    return result


def tema(prices: Sequence[float], period: int) -> list[float]:
    """Triple Exponential Moving Average (TEMA): 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))."""
    ema1 = ema(prices, period)
    v1 = period - 1
    ema2_raw = ema(ema1[v1:], period)
    ema2 = [float("nan")] * (v1 + period - 1) + ema2_raw[period - 1:]

    v2 = (v1 + period - 1)
    ema3_raw = ema(ema2[v2:], period)
    ema3 = [float("nan")] * (v2 + period - 1) + ema3_raw[period - 1:]

    n = len(prices)
    result = []
    for i in range(n):
        if math.isnan(ema1[i]) or math.isnan(ema2[i]) or math.isnan(ema3[i]):
            result.append(float("nan"))
        else:
            result.append(3.0 * ema1[i] - 3.0 * ema2[i] + ema3[i])
    return result


# ============================================================================
# 2. Trend & Oscillators
# ============================================================================

def macd(
    prices: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """Moving Average Convergence Divergence (MACD).
    Returns (macd_line, signal_line, histogram).
    """
    n = len(prices)
    fast_ema = ema(prices, fast_period)
    slow_ema = ema(prices, slow_period)

    macd_line = []
    for f, s in zip(fast_ema, slow_ema):
        if math.isnan(f) or math.isnan(s):
            macd_line.append(float("nan"))
        else:
            macd_line.append(f - s)

    # Filter out leading NaNs to calculate signal line
    first_valid = slow_period - 1
    if n <= first_valid:
        return macd_line, [float("nan")] * n, [float("nan")] * n

    valid_macd = macd_line[first_valid:]
    raw_signal = ema(valid_macd, signal_period)
    signal_line = [float("nan")] * (first_valid + signal_period - 1) + raw_signal[signal_period - 1:]

    histogram = []
    for m, sig in zip(macd_line, signal_line):
        if math.isnan(m) or math.isnan(sig):
            histogram.append(float("nan"))
        else:
            histogram.append(m - sig)

    return macd_line, signal_line, histogram


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> tuple[list[float], list[float], list[float]]:
    """Average Directional Index (ADX) with +DI and -DI.
    Returns (plus_di, minus_di, adx).
    """
    n = len(closes)
    if n < period + 1:
        nan_list = [float("nan")] * n
        return nan_list, nan_list, nan_list

    tr_list: list[float] = [0.0]
    plus_dm_list: list[float] = [0.0]
    minus_dm_list: list[float] = [0.0]

    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]

        # True Range
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

        # Directional Movement
        up_move = h - prev_h
        down_move = prev_l - l

        if up_move > down_move and up_move > 0:
            plus_dm_list.append(up_move)
        else:
            plus_dm_list.append(0.0)

        if down_move > up_move and down_move > 0:
            minus_dm_list.append(down_move)
        else:
            minus_dm_list.append(0.0)

    # Wilder's Smoothing for TR and DMs
    smooth_tr = [float("nan")] * n
    smooth_plus_dm = [float("nan")] * n
    smooth_minus_dm = [float("nan")] * n

    smooth_tr[period] = sum(tr_list[1 : period + 1])
    smooth_plus_dm[period] = sum(plus_dm_list[1 : period + 1])
    smooth_minus_dm[period] = sum(minus_dm_list[1 : period + 1])

    for i in range(period + 1, n):
        smooth_tr[i] = smooth_tr[i - 1] - (smooth_tr[i - 1] / period) + tr_list[i]
        smooth_plus_dm[i] = smooth_plus_dm[i - 1] - (smooth_plus_dm[i - 1] / period) + plus_dm_list[i]
        smooth_minus_dm[i] = smooth_minus_dm[i - 1] - (smooth_minus_dm[i - 1] / period) + minus_dm_list[i]

    plus_di = [float("nan")] * n
    minus_di = [float("nan")] * n
    dx_list = [float("nan")] * n

    for i in range(period, n):
        tr_val = smooth_tr[i]
        if tr_val > 0:
            p_di = (smooth_plus_dm[i] / tr_val) * 100.0
            m_di = (smooth_minus_dm[i] / tr_val) * 100.0
        else:
            p_di = 0.0
            m_di = 0.0

        plus_di[i] = p_di
        minus_di[i] = m_di

        di_sum = p_di + m_di
        if di_sum > 0:
            dx = (abs(p_di - m_di) / di_sum) * 100.0
        else:
            dx = 0.0
        dx_list[i] = dx

    # Smooth DX to get ADX
    adx_list = [float("nan")] * n
    start_adx_idx = 2 * period - 1
    if n > start_adx_idx:
        valid_dxs = [dx_list[i] for i in range(period, start_adx_idx + 1)]
        adx_list[start_adx_idx] = sum(valid_dxs) / period
        for i in range(start_adx_idx + 1, n):
            adx_list[i] = (adx_list[i - 1] * (period - 1) + dx_list[i]) / period

    return plus_di, minus_di, adx_list


def supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[list[float], list[int]]:
    """Supertrend indicator.
    Returns (supertrend_values, direction_1_bullish_minus1_bearish).
    """
    n = len(closes)
    atr_vals = atr(highs, lows, closes, period)
    st = [float("nan")] * n
    direction = [0] * n

    upper_band = [0.0] * n
    lower_band = [0.0] * n

    for i in range(period, n):
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * atr_vals[i]
        basic_lower = hl2 - multiplier * atr_vals[i]

        if i == period:
            upper_band[i] = basic_upper
            lower_band[i] = basic_lower
            direction[i] = 1 if closes[i] > basic_upper else -1
            st[i] = lower_band[i] if direction[i] == 1 else upper_band[i]
            continue

        prev_upper = upper_band[i - 1]
        prev_lower = lower_band[i - 1]

        if basic_upper < prev_upper or closes[i - 1] > prev_upper:
            upper_band[i] = basic_upper
        else:
            upper_band[i] = prev_upper

        if basic_lower > prev_lower or closes[i - 1] < prev_lower:
            lower_band[i] = basic_lower
        else:
            lower_band[i] = prev_lower

        prev_st = st[i - 1]
        prev_dir = direction[i - 1]

        if prev_dir == 1:
            if closes[i] < lower_band[i]:
                direction[i] = -1
                st[i] = upper_band[i]
            else:
                direction[i] = 1
                st[i] = lower_band[i]
        else:
            if closes[i] > upper_band[i]:
                direction[i] = 1
                st[i] = lower_band[i]
            else:
                direction[i] = -1
                st[i] = upper_band[i]

    return st, direction


# ============================================================================
# 3. Momentum Oscillators
# ============================================================================

def rsi(prices: Sequence[float], period: int = 14) -> list[float]:
    """Relative Strength Index (RSI) using Wilder's exponential smoothing."""
    n = len(prices)
    if period <= 0 or n < period + 1:
        return [float("nan")] * n

    gains = [0.0] * n
    losses = [0.0] * n

    for i in range(1, n):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains[i] = delta
        else:
            losses[i] = -delta

    result = [float("nan")] * n
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> tuple[list[float], list[float]]:
    """Stochastic Oscillator (%K, %D).
    Returns (fast_k / smooth_k, d_line).
    """
    n = len(closes)
    if n < k_period:
        nan_list = [float("nan")] * n
        return nan_list, nan_list

    raw_k = [float("nan")] * (k_period - 1)
    for i in range(k_period - 1, n):
        h_win = max(highs[i - k_period + 1 : i + 1])
        l_win = min(lows[i - k_period + 1 : i + 1])
        denom = h_win - l_win
        if denom > 0:
            raw_k.append(((closes[i] - l_win) / denom) * 100.0)
        else:
            raw_k.append(50.0)

    # Smooth %K if smooth_k > 1
    if smooth_k > 1:
        smooth_k_vals = sma(raw_k[k_period - 1:], smooth_k)
        k_line = [float("nan")] * (k_period - 1 + smooth_k - 1) + smooth_k_vals[smooth_k - 1:]
    else:
        k_line = raw_k

    # %D is SMA of %K
    first_valid_k = k_period - 1 + (smooth_k - 1 if smooth_k > 1 else 0)
    if n <= first_valid_k:
        return k_line, [float("nan")] * n

    valid_k = k_line[first_valid_k:]
    raw_d = sma(valid_k, d_period)
    d_line = [float("nan")] * (first_valid_k + d_period - 1) + raw_d[d_period - 1:]

    return k_line, d_line


def stochastic_rsi(
    prices: Sequence[float],
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> tuple[list[float], list[float]]:
    """Stochastic RSI."""
    rsi_vals = rsi(prices, rsi_period)
    n = len(prices)
    valid_start = rsi_period
    if n < valid_start + stoch_period:
        nan_list = [float("nan")] * n
        return nan_list, nan_list

    stoch_rsi_raw = [float("nan")] * (valid_start + stoch_period - 1)
    for i in range(valid_start + stoch_period - 1, n):
        rsi_win = rsi_vals[i - stoch_period + 1 : i + 1]
        h_rsi = max(rsi_win)
        l_rsi = min(rsi_win)
        denom = h_rsi - l_rsi
        if denom > 0:
            stoch_rsi_raw.append((rsi_vals[i] - l_rsi) / denom * 100.0)
        else:
            stoch_rsi_raw.append(50.0)

    k_vals = sma(stoch_rsi_raw[valid_start + stoch_period - 1:], k_period)
    k_line = [float("nan")] * (valid_start + stoch_period - 1 + k_period - 1) + k_vals[k_period - 1:]

    valid_k_idx = valid_start + stoch_period - 1 + k_period - 1
    if n <= valid_k_idx:
        return k_line, [float("nan")] * n

    d_vals = sma(k_line[valid_k_idx:], d_period)
    d_line = [float("nan")] * (valid_k_idx + d_period - 1) + d_vals[d_period - 1:]

    return k_line, d_line


def roc(prices: Sequence[float], period: int = 12) -> list[float]:
    """Rate of Change (ROC) percentage: ((price - price[t-n]) / price[t-n]) * 100."""
    n = len(prices)
    if period <= 0 or n < period + 1:
        return [float("nan")] * n

    result = [float("nan")] * period
    for i in range(period, n):
        prev = prices[i - period]
        if prev != 0:
            result.append(((prices[i] - prev) / prev) * 100.0)
        else:
            result.append(0.0)
    return result


def mfi(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Money Flow Index (MFI). Volume-weighted RSI."""
    n = len(closes)
    if n < period + 1:
        return [float("nan")] * n

    typical_prices = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
    raw_money_flow = [tp * v for tp, v in zip(typical_prices, volumes)]

    pos_flow = [0.0] * n
    neg_flow = [0.0] * n

    for i in range(1, n):
        if typical_prices[i] > typical_prices[i - 1]:
            pos_flow[i] = raw_money_flow[i]
        elif typical_prices[i] < typical_prices[i - 1]:
            neg_flow[i] = raw_money_flow[i]

    result = [float("nan")] * n
    for i in range(period, n):
        pos_sum = sum(pos_flow[i - period + 1 : i + 1])
        neg_sum = sum(neg_flow[i - period + 1 : i + 1])

        if neg_sum == 0:
            result[i] = 100.0
        else:
            mfr = pos_sum / neg_sum
            result[i] = 100.0 - (100.0 / (1.0 + mfr))

    return result


# ============================================================================
# 4. Volatility Indicators
# ============================================================================

def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Average True Range (ATR) using Wilder's smoothing."""
    n = len(closes)
    if period <= 0 or n < period:
        return [float("nan")] * n

    tr_list = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)

    result = [float("nan")] * (period - 1)
    current_atr = sum(tr_list[:period]) / period
    result.append(current_atr)

    for i in range(period, n):
        current_atr = (current_atr * (period - 1) + tr_list[i]) / period
        result.append(current_atr)

    return result


def bollinger_bands(
    prices: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Bollinger Bands.
    Returns (upper_band, middle_band, lower_band, percent_b, bandwidth).
    """
    n = len(prices)
    middle = sma(prices, period)
    upper = [float("nan")] * n
    lower = [float("nan")] * n
    pct_b = [float("nan")] * n
    bandwidth = [float("nan")] * n

    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        m = middle[i]
        variance = sum((x - m) ** 2 for x in window) / period
        stdev = math.sqrt(variance)

        u = m + num_std * stdev
        l = m - num_std * stdev

        upper[i] = u
        lower[i] = l

        if (u - l) > 0:
            pct_b[i] = (prices[i] - l) / (u - l)
        else:
            pct_b[i] = 0.5

        if m > 0:
            bandwidth[i] = (u - l) / m
        else:
            bandwidth[i] = 0.0

    return upper, middle, lower, pct_b, bandwidth


def keltner_channels(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    """Keltner Channels.
    Returns (upper_channel, middle_channel_ema, lower_channel).
    """
    middle = ema(closes, ema_period)
    atr_vals = atr(highs, lows, closes, atr_period)
    n = len(closes)

    upper = [float("nan")] * n
    lower = [float("nan")] * n

    for i in range(n):
        if not math.isnan(middle[i]) and not math.isnan(atr_vals[i]):
            upper[i] = middle[i] + multiplier * atr_vals[i]
            lower[i] = middle[i] - multiplier * atr_vals[i]

    return upper, middle, lower


def donchian_channels(
    highs: Sequence[float],
    lows: Sequence[float],
    period: int = 20,
) -> tuple[list[float], list[float], list[float]]:
    """Donchian Channels.
    Returns (upper_channel, middle_channel, lower_channel).
    """
    n = len(highs)
    if period <= 0 or n < period:
        nan_list = [float("nan")] * n
        return nan_list, nan_list, nan_list

    upper = [float("nan")] * (period - 1)
    lower = [float("nan")] * (period - 1)
    middle = [float("nan")] * (period - 1)

    for i in range(period - 1, n):
        u = max(highs[i - period + 1 : i + 1])
        l = min(lows[i - period + 1 : i + 1])
        upper.append(u)
        lower.append(l)
        middle.append((u + l) / 2.0)

    return upper, middle, lower


def historical_volatility(
    prices: Sequence[float],
    period: int = 20,
    trading_days: int = 252,
) -> list[float]:
    """Annualized Historical Volatility of logarithmic returns."""
    n = len(prices)
    if n < period + 1:
        return [float("nan")] * n

    log_returns = [0.0]
    for i in range(1, n):
        if prices[i - 1] > 0 and prices[i] > 0:
            log_returns.append(math.log(prices[i] / prices[i - 1]))
        else:
            log_returns.append(0.0)

    result = [float("nan")] * period
    annual_factor = math.sqrt(trading_days)

    for i in range(period, n):
        window = log_returns[i - period + 1 : i + 1]
        mean_ret = sum(window) / period
        var = sum((r - mean_ret) ** 2 for r in window) / (period - 1)
        result.append(math.sqrt(var) * annual_factor)

    return result


# ============================================================================
# 5. Volume Indicators
# ============================================================================

def obv(closes: Sequence[float], volumes: Sequence[float]) -> list[float]:
    """On-Balance Volume (OBV)."""
    n = len(closes)
    if n == 0:
        return []

    result = [volumes[0]]
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            result.append(result[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            result.append(result[-1] - volumes[i])
        else:
            result.append(result[-1])
    return result


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[float]:
    """Cumulative Volume-Weighted Average Price (VWAP)."""
    n = len(closes)
    if n == 0:
        return []

    result = []
    cum_pv = 0.0
    cum_vol = 0.0

    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3.0
        cum_pv += tp * v
        cum_vol += v
        if cum_vol > 0:
            result.append(cum_pv / cum_vol)
        else:
            result.append(tp)

    return result


def chaikin_money_flow(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Chaikin Money Flow (CMF)."""
    n = len(closes)
    if n < period:
        return [float("nan")] * n

    mf_vol = []
    for h, l, c, v in zip(highs, lows, closes, volumes):
        denom = h - l
        if denom > 0:
            clv = ((c - l) - (h - c)) / denom
        else:
            clv = 0.0
        mf_vol.append(clv * v)

    result = [float("nan")] * (period - 1)
    for i in range(period - 1, n):
        sum_mfv = sum(mf_vol[i - period + 1 : i + 1])
        sum_vol = sum(volumes[i - period + 1 : i + 1])
        if sum_vol > 0:
            result.append(sum_mfv / sum_vol)
        else:
            result.append(0.0)

    return result


# ============================================================================
# 6. Price Action, Pivots & Candlestick Patterns
# ============================================================================

def pivot_points_standard(high: float, low: float, close: float) -> dict[str, float]:
    """Standard Floor Pivot Points."""
    p = (high + low + close) / 3.0
    r1 = 2.0 * p - low
    s1 = 2.0 * p - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    r3 = high + 2.0 * (p - low)
    s3 = low - 2.0 * (high - p)
    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def pivot_points_fibonacci(high: float, low: float, close: float) -> dict[str, float]:
    """Fibonacci Pivot Points."""
    p = (high + low + close) / 3.0
    diff = high - low
    r1 = p + 0.382 * diff
    r2 = p + 0.618 * diff
    r3 = p + 1.000 * diff
    s1 = p - 0.382 * diff
    s2 = p - 0.618 * diff
    s3 = p - 1.000 * diff
    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def pivot_points_camarilla(high: float, low: float, close: float) -> dict[str, float]:
    """Camarilla Pivot Points."""
    diff = high - low
    p = (high + low + close) / 3.0
    r4 = close + diff * (1.1 / 2.0)
    r3 = close + diff * (1.1 / 4.0)
    r2 = close + diff * (1.1 / 6.0)
    r1 = close + diff * (1.1 / 12.0)
    s1 = close - diff * (1.1 / 12.0)
    s2 = close - diff * (1.1 / 6.0)
    s3 = close - diff * (1.1 / 4.0)
    s4 = close - diff * (1.1 / 2.0)
    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "R4": r4, "S1": s1, "S2": s2, "S3": s3, "S4": s4}


def candlestick_patterns(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> dict[str, list[bool]]:
    """Identifies major single and multi-candle price action patterns."""
    n = len(closes)
    doji = [False] * n
    hammer = [False] * n
    shooting_star = [False] * n
    bullish_engulfing = [False] * n
    bearish_engulfing = [False] * n
    morning_star = [False] * n
    evening_star = [False] * n

    for i in range(n):
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        body = abs(c - o)
        candle_range = h - l

        if candle_range <= 0:
            continue

        # Doji: body < 10% of total range
        if body / candle_range < 0.10:
            doji[i] = True

        # Lower & Upper shadows
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l

        # Hammer: Small body, lower shadow >= 2x body, upper shadow <= 0.2x body
        if body > 0 and lower_shadow >= 2.0 * body and upper_shadow <= 0.2 * body:
            hammer[i] = True

        # Shooting Star: Small body, upper shadow >= 2x body, lower shadow <= 0.2x body
        if body > 0 and upper_shadow >= 2.0 * body and lower_shadow <= 0.2 * body:
            shooting_star[i] = True

        # Two-bar patterns
        if i >= 1:
            prev_o = opens[i - 1]
            prev_c = closes[i - 1]

            # Bullish Engulfing: previous bearish, current bullish engulfs previous body
            if prev_c < prev_o and c > o and c >= prev_o and o <= prev_c:
                bullish_engulfing[i] = True

            # Bearish Engulfing: previous bullish, current bearish engulfs previous body
            if prev_c > prev_o and c < o and c <= prev_o and o >= prev_c:
                bearish_engulfing[i] = True

        # Three-bar patterns (Morning Star / Evening Star)
        if i >= 2:
            p2_o, p2_c = opens[i - 2], closes[i - 2]
            p1_o, p1_c, p1_h, p1_l = opens[i - 1], closes[i - 1], highs[i - 1], lows[i - 1]
            p1_body = abs(p1_c - p1_o)
            p1_range = p1_h - p1_l

            # Morning Star: Bearish -> Small Star -> Strong Bullish closing > midpoint of first
            if p2_c < p2_o and (p1_range > 0 and p1_body / p1_range < 0.3) and c > o:
                mid_p2 = (p2_o + p2_c) / 2.0
                if c > mid_p2:
                    morning_star[i] = True

            # Evening Star: Bullish -> Small Star -> Strong Bearish closing < midpoint of first
            if p2_c > p2_o and (p1_range > 0 and p1_body / p1_range < 0.3) and c < o:
                mid_p2 = (p2_o + p2_c) / 2.0
                if c < mid_p2:
                    evening_star[i] = True

    return {
        "doji": doji,
        "hammer": hammer,
        "shooting_star": shooting_star,
        "bullish_engulfing": bullish_engulfing,
        "bearish_engulfing": bearish_engulfing,
        "morning_star": morning_star,
        "evening_star": evening_star,
    }
