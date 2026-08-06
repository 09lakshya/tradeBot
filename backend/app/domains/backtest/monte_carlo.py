"""Monte Carlo Simulator: Trade Return Resampling, Block Bootstrap, and Ruin Probability Estimation."""
from dataclasses import dataclass
from decimal import Decimal
import math
import random
from typing import Any

from app.domains.backtest.schemas import MonteCarloConfig


def _quantile(sorted_data: list[float], q: float) -> float:
    """Computes exact percentile from sorted data."""
    if not sorted_data:
        return 0.0
    idx = (len(sorted_data) - 1) * q
    lower = int(math.floor(idx))
    upper = int(math.ceil(idx))
    weight = idx - lower
    return sorted_data[lower] * (1.0 - weight) + sorted_data[upper] * weight


@dataclass
class MonteCarloResult:
    """Summary of Monte Carlo simulation distributions."""
    iterations: int
    random_seed: int
    terminal_equity_quantiles: dict[str, float]  # "p5", "p25", "p50", "p75", "p95"
    max_drawdown_quantiles: dict[str, float]
    sharpe_quantiles: dict[str, float]
    probability_of_ruin: float
    var_95: float
    cvar_95: float
    sample_equity_paths: list[list[float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "random_seed": self.random_seed,
            "terminal_equity_quantiles": {k: round(v, 2) for k, v in self.terminal_equity_quantiles.items()},
            "max_drawdown_quantiles": {k: round(v, 4) for k, v in self.max_drawdown_quantiles.items()},
            "sharpe_quantiles": {k: round(v, 4) for k, v in self.sharpe_quantiles.items()},
            "probability_of_ruin": round(self.probability_of_ruin, 4),
            "var_95": round(self.var_95, 4),
            "cvar_95": round(self.cvar_95, 4),
            "sample_equity_paths": self.sample_equity_paths,
        }


class MonteCarloSimulator:
    """Stochastic Monte Carlo simulation for strategy risk & path robustness."""

    @staticmethod
    def simulate(
        trade_pnls: list[float],
        initial_capital: float = 100000.0,
        config: MonteCarloConfig | None = None,
    ) -> MonteCarloResult:
        """Run seeded Monte Carlo trade sequence resampling."""
        cfg = config or MonteCarloConfig()
        rng = random.Random(cfg.random_seed)

        if not trade_pnls or len(trade_pnls) < 2:
            return MonteCarloSimulator._empty_result(cfg.iterations, cfg.random_seed, initial_capital)

        n_trades = len(trade_pnls)
        terminal_equities: list[float] = []
        max_drawdowns: list[float] = []
        sharpes: list[float] = []
        ruined_paths = 0
        sample_paths: list[list[float]] = []

        block_size = max(1, min(cfg.block_size, n_trades // 2)) if cfg.resample_method == "block_bootstrap" else 1

        for iter_idx in range(cfg.iterations):
            # Resample trade returns sequence
            resampled_pnls: list[float] = []
            while len(resampled_pnls) < n_trades:
                if cfg.resample_method == "block_bootstrap" and n_trades > block_size:
                    start_idx = rng.randint(0, n_trades - block_size)
                    resampled_pnls.extend(trade_pnls[start_idx:start_idx + block_size])
                else:
                    resampled_pnls.append(rng.choice(trade_pnls))

            resampled_pnls = resampled_pnls[:n_trades]

            # Construct synthetic equity curve
            equity = initial_capital
            peak = equity
            max_dd = 0.0
            path: list[float] = [equity]

            for pnl in resampled_pnls:
                equity += pnl
                path.append(equity)
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd

            terminal_equities.append(equity)
            max_drawdowns.append(max_dd)

            # Check ruin threshold
            if max_dd >= float(cfg.ruin_drawdown_threshold):
                ruined_paths += 1

            # Estimate Sharpe for this path
            returns = [(path[i] - path[i - 1]) / path[i - 1] for i in range(1, len(path)) if path[i - 1] > 0]
            if len(returns) > 1:
                mean_r = sum(returns) / len(returns)
                var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
                std_r = math.sqrt(var_r) if var_r > 0 else 1e-6
                sharpe = (mean_r / std_r) * math.sqrt(252)
            else:
                sharpe = 0.0
            sharpes.append(sharpe)

            # Keep first 10 paths for visualization
            if iter_idx < 10:
                sample_paths.append([round(e, 2) for e in path])

        # Compute Quantiles
        terminal_equities.sort()
        max_drawdowns.sort()
        sharpes.sort()

        p_ruin = ruined_paths / cfg.iterations

        # Value at Risk (VaR 95%) and Conditional VaR (CVaR 95%)
        # Losses relative to initial capital
        loss_pcts = sorted([(initial_capital - eq) / initial_capital for eq in terminal_equities])
        var_95 = max(0.0, _quantile(loss_pcts, 0.95))
        tail_losses = [l for l in loss_pcts if l >= var_95]
        cvar_95 = sum(tail_losses) / len(tail_losses) if tail_losses else var_95

        return MonteCarloResult(
            iterations=cfg.iterations,
            random_seed=cfg.random_seed,
            terminal_equity_quantiles={
                "p5": _quantile(terminal_equities, 0.05),
                "p25": _quantile(terminal_equities, 0.25),
                "p50": _quantile(terminal_equities, 0.50),
                "p75": _quantile(terminal_equities, 0.75),
                "p95": _quantile(terminal_equities, 0.95),
            },
            max_drawdown_quantiles={
                "p5": _quantile(max_drawdowns, 0.05),
                "p25": _quantile(max_drawdowns, 0.25),
                "p50": _quantile(max_drawdowns, 0.50),
                "p75": _quantile(max_drawdowns, 0.75),
                "p95": _quantile(max_drawdowns, 0.95),
            },
            sharpe_quantiles={
                "p5": _quantile(sharpes, 0.05),
                "p25": _quantile(sharpes, 0.25),
                "p50": _quantile(sharpes, 0.50),
                "p75": _quantile(sharpes, 0.75),
                "p95": _quantile(sharpes, 0.95),
            },
            probability_of_ruin=p_ruin,
            var_95=var_95,
            cvar_95=cvar_95,
            sample_equity_paths=sample_paths,
        )

    @staticmethod
    def _empty_result(iterations: int, random_seed: int, initial_capital: float) -> MonteCarloResult:
        return MonteCarloResult(
            iterations=iterations,
            random_seed=random_seed,
            terminal_equity_quantiles={
                "p5": initial_capital, "p25": initial_capital, "p50": initial_capital,
                "p75": initial_capital, "p95": initial_capital,
            },
            max_drawdown_quantiles={"p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0},
            sharpe_quantiles={"p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0},
            probability_of_ruin=0.0,
            var_95=0.0,
            cvar_95=0.0,
            sample_equity_paths=[],
        )
