"""Comprehensive Financial Performance Metrics & Statistical Significance Calculator."""
from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


@dataclass
class PerformanceReport:
    """Structured report containing all calculated performance metrics."""
    # Returns
    total_return_pct: float
    cagr_pct: float
    annualized_volatility_pct: float
    
    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float
    gain_to_pain_ratio: float
    
    # Drawdowns
    max_drawdown_pct: float
    avg_drawdown_pct: float
    max_drawdown_duration_days: int
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy: float
    avg_trade_pnl: float
    payoff_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    
    # Benchmark metrics
    benchmark_return_pct: float | None
    beta: float | None
    alpha: float | None
    tracking_error: float | None
    information_ratio: float | None
    
    # Statistical Significance & Anti-Overfitting
    probabilistic_sharpe_ratio: float
    deflated_sharpe_ratio: float
    probability_of_backtest_overfitting: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return_pct": round(self.total_return_pct, 4),
            "cagr_pct": round(self.cagr_pct, 4),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "omega_ratio": round(self.omega_ratio, 4),
            "gain_to_pain_ratio": round(self.gain_to_pain_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "avg_drawdown_pct": round(self.avg_drawdown_pct, 4),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate_pct, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "avg_trade_pnl": round(self.avg_trade_pnl, 4),
            "payoff_ratio": round(self.payoff_ratio, 4),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "benchmark_return_pct": round(self.benchmark_return_pct, 4) if self.benchmark_return_pct is not None else None,
            "beta": round(self.beta, 4) if self.beta is not None else None,
            "alpha": round(self.alpha, 4) if self.alpha is not None else None,
            "tracking_error": round(self.tracking_error, 4) if self.tracking_error is not None else None,
            "information_ratio": round(self.information_ratio, 4) if self.information_ratio is not None else None,
            "probabilistic_sharpe_ratio": round(self.probabilistic_sharpe_ratio, 4),
            "deflated_sharpe_ratio": round(self.deflated_sharpe_ratio, 4),
            "probability_of_backtest_overfitting": round(self.probability_of_backtest_overfitting, 4),
        }


class PerformanceMetricsCalculator:
    """Pure mathematical calculator for quantitative backtest performance."""

    @staticmethod
    def calculate(
        equity_series: list[float],
        trade_pnls: list[float] | None = None,
        benchmark_series: list[float] | None = None,
        risk_free_rate: float = 0.05,  # 5% annual risk-free rate
        num_trials: int = 1,          # Number of parameter trials for DSR calculation
        annualization_factor: int = 252,
    ) -> PerformanceReport:
        """Computes comprehensive performance metrics from equity curve."""
        trade_pnls = trade_pnls or []
        if len(equity_series) < 2:
            return PerformanceMetricsCalculator._empty_report()

        initial_equity = equity_series[0]
        final_equity = equity_series[-1]
        n_periods = len(equity_series) - 1

        # 1. Period Returns
        returns = []
        for i in range(1, len(equity_series)):
            prev = equity_series[i - 1]
            curr = equity_series[i]
            ret = (curr - prev) / prev if prev > 0 else 0.0
            returns.append(ret)

        total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0 if initial_equity > 0 else 0.0
        years = max(n_periods / annualization_factor, 1.0 / annualization_factor)
        cagr_pct = (((final_equity / initial_equity) ** (1.0 / years)) - 1.0) * 100.0 if initial_equity > 0 and final_equity > 0 else total_return_pct

        # 2. Volatility & Risk-Adjusted
        mean_ret = sum(returns) / len(returns) if returns else 0.0
        rf_daily = risk_free_rate / annualization_factor
        excess_returns = [r - rf_daily for r in returns]
        
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 0.0
        std = math.sqrt(var) if var > 0 else 1e-6
        ann_volatility_pct = std * math.sqrt(annualization_factor) * 100.0

        sharpe = (sum(excess_returns) / len(excess_returns)) / std * math.sqrt(annualization_factor) if std > 0 else 0.0

        downside_diffs = [min(0.0, r - rf_daily) for r in returns]
        downside_var = sum(d ** 2 for d in downside_diffs) / len(returns) if returns else 0.0
        downside_std = math.sqrt(downside_var) if downside_var > 0 else 1e-6
        sortino = (sum(excess_returns) / len(excess_returns)) / downside_std * math.sqrt(annualization_factor) if downside_std > 0 else 0.0

        # Omega ratio
        pos_excess = sum(max(0.0, r - rf_daily) for r in returns)
        neg_excess = sum(max(0.0, rf_daily - r) for r in returns)
        omega = pos_excess / neg_excess if neg_excess > 0 else 10.0

        # 3. Drawdown Analysis
        peak = equity_series[0]
        drawdowns = []
        dd_durations = []
        current_dd_duration = 0

        for eq in equity_series:
            if eq > peak:
                peak = eq
                current_dd_duration = 0
            else:
                current_dd_duration += 1
            dd = (peak - eq) / peak if peak > 0 else 0.0
            drawdowns.append(dd)
            dd_durations.append(current_dd_duration)

        max_dd_pct = max(drawdowns) * 100.0 if drawdowns else 0.0
        avg_dd_pct = (sum(drawdowns) / len(drawdowns)) * 100.0 if drawdowns else 0.0
        max_dd_duration = max(dd_durations) if dd_durations else 0

        calmar = (cagr_pct / max_dd_pct) if max_dd_pct > 0 else 10.0

        # 4. Trade Statistics
        total_trades = len(trade_pnls)
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate_pct = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (10.0 if gross_profit > 0 else 1.0)
        gain_to_pain = (sum(trade_pnls) / gross_loss) if gross_loss > 0 else 10.0

        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (abs(sum(losses)) / loss_count) if loss_count > 0 else 0.0
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else (1.0 if avg_win > 0 else 0.0)

        expectancy = ((win_rate_pct / 100.0) * avg_win) - (((100.0 - win_rate_pct) / 100.0) * avg_loss)
        avg_trade_pnl = sum(trade_pnls) / total_trades if total_trades > 0 else 0.0

        # Consecutive streaks
        max_consec_wins = 0
        max_consec_losses = 0
        curr_wins = 0
        curr_losses = 0
        for p in trade_pnls:
            if p > 0:
                curr_wins += 1
                curr_losses = 0
                max_consec_wins = max(max_consec_wins, curr_wins)
            elif p < 0:
                curr_losses += 1
                curr_wins = 0
                max_consec_losses = max(max_consec_losses, curr_losses)

        # 5. Benchmark Comparison
        benchmark_return_pct = None
        beta = None
        alpha = None
        tracking_error = None
        info_ratio = None

        if benchmark_series and len(benchmark_series) == len(equity_series):
            bench_returns = []
            for i in range(1, len(benchmark_series)):
                b_prev = benchmark_series[i - 1]
                b_curr = benchmark_series[i]
                bench_returns.append((b_curr - b_prev) / b_prev if b_prev > 0 else 0.0)

            b_init = benchmark_series[0]
            b_final = benchmark_series[-1]
            benchmark_return_pct = ((b_final - b_init) / b_init) * 100.0 if b_init > 0 else 0.0

            b_mean = sum(bench_returns) / len(bench_returns) if bench_returns else 0.0
            cov = sum((returns[i] - mean_ret) * (bench_returns[i] - b_mean) for i in range(len(returns))) / len(returns) if len(returns) > 1 else 0.0
            b_var = sum((b - b_mean) ** 2 for b in bench_returns) / len(bench_returns) if len(bench_returns) > 1 else 0.0
            
            beta = (cov / b_var) if b_var > 0 else 1.0
            alpha = (total_return_pct - (beta * benchmark_return_pct))

            active_returns = [returns[i] - bench_returns[i] for i in range(len(returns))]
            active_var = sum((a - (sum(active_returns) / len(active_returns))) ** 2 for a in active_returns) / len(active_returns) if len(active_returns) > 1 else 0.0
            tracking_error = math.sqrt(active_var) * math.sqrt(annualization_factor) * 100.0
            info_ratio = (sum(active_returns) / len(active_returns) * math.sqrt(annualization_factor)) / (math.sqrt(active_var) if active_var > 0 else 1e-6)

        # 6. Statistical Significance & Anti-Overfitting (PSR & DSR)
        # Higher moments (Skewness & Kurtosis)
        n = len(returns)
        if n > 3 and std > 0:
            skew = sum(((r - mean_ret) / std) ** 3 for r in returns) / n
            kurt = sum(((r - mean_ret) / std) ** 4 for r in returns) / n
        else:
            skew = 0.0
            kurt = 3.0

        # Probabilistic Sharpe Ratio (PSR) vs SR benchmark 0.0
        sr_benchmark = 0.0
        psr_denom = math.sqrt(max(1e-6, 1.0 - (skew * (sharpe / math.sqrt(annualization_factor))) + (((kurt - 1.0) / 4.0) * (sharpe / math.sqrt(annualization_factor)) ** 2)))
        psr_stat = ((sharpe / math.sqrt(annualization_factor) - sr_benchmark) * math.sqrt(n - 1)) / psr_denom
        psr = _normal_cdf(psr_stat)

        # Deflated Sharpe Ratio (DSR) adjusting for K parameter trials
        # Expected max Sharpe under null hypothesis (Euler-Mascheroni approximation)
        if num_trials > 1:
            gamma = 0.5772156649
            sr_null_daily = math.sqrt(2.0 * math.log(num_trials)) + (gamma / math.sqrt(2.0 * math.log(num_trials)))
            sr_null_ann = sr_null_daily * math.sqrt(annualization_factor) * 0.1  # normalized bound
            dsr_stat = ((sharpe - sr_null_ann) * math.sqrt(n - 1)) / (psr_denom * math.sqrt(annualization_factor))
            dsr = _normal_cdf(dsr_stat)
            pbo = max(0.0, min(1.0, 1.0 - dsr))
        else:
            dsr = psr
            pbo = max(0.0, min(1.0, 1.0 - psr))

        return PerformanceReport(
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            annualized_volatility_pct=ann_volatility_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            omega_ratio=omega,
            gain_to_pain_ratio=gain_to_pain,
            max_drawdown_pct=max_dd_pct,
            avg_drawdown_pct=avg_dd_pct,
            max_drawdown_duration_days=max_dd_duration,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_trade_pnl=avg_trade_pnl,
            payoff_ratio=payoff_ratio,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            benchmark_return_pct=benchmark_return_pct,
            beta=beta,
            alpha=alpha,
            tracking_error=tracking_error,
            information_ratio=info_ratio,
            probabilistic_sharpe_ratio=psr,
            deflated_sharpe_ratio=dsr,
            probability_of_backtest_overfitting=pbo,
        )

    @staticmethod
    def _empty_report() -> PerformanceReport:
        return PerformanceReport(
            total_return_pct=0.0,
            cagr_pct=0.0,
            annualized_volatility_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            omega_ratio=0.0,
            gain_to_pain_ratio=0.0,
            max_drawdown_pct=0.0,
            avg_drawdown_pct=0.0,
            max_drawdown_duration_days=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            avg_trade_pnl=0.0,
            payoff_ratio=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            benchmark_return_pct=None,
            beta=None,
            alpha=None,
            tracking_error=None,
            information_ratio=None,
            probabilistic_sharpe_ratio=0.0,
            deflated_sharpe_ratio=0.0,
            probability_of_backtest_overfitting=0.5,
        )
