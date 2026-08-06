"""Walk-Forward Validation Engine supporting Rolling, Expanding Windows, and Purged OOS Stitching."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.domains.backtest.enums import WindowType
from app.domains.backtest.exceptions import InvalidWindowSpecError
from app.domains.backtest.schemas import WalkForwardConfig
from app.domains.metrics.calculator import PerformanceMetricsCalculator, PerformanceReport


@dataclass(frozen=True)
class WalkForwardWindow:
    """Specification of an In-Sample (IS) and Out-of-Sample (OOS) time window."""
    window_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    purge_start: date | None = None
    purge_end: date | None = None
    embargo_start: date | None = None
    embargo_end: date | None = None


@dataclass
class WalkForwardSegmentResult:
    """Execution results for an individual walk-forward window."""
    window: WalkForwardWindow
    is_metrics: dict[str, Any]
    oos_metrics: dict[str, Any]
    is_equity_curve: list[dict[str, Any]]
    oos_equity_curve: list[dict[str, Any]]
    wfe_ratio: float  # Walk-Forward Efficiency (OOS Return / IS Return)


@dataclass
class WalkForwardValidationSummary:
    """Complete summary across all walk-forward validation windows."""
    total_windows: int
    window_type: WindowType
    mean_is_sharpe: float
    mean_oos_sharpe: float
    mean_wfe_ratio: float
    concatenated_oos_metrics: dict[str, Any]
    concatenated_oos_equity_curve: list[dict[str, Any]]
    window_results: list[WalkForwardSegmentResult]


class WalkForwardEngine:
    """Generates and manages walk-forward validation partitions."""

    @staticmethod
    def generate_windows(
        start_date: date,
        end_date: date,
        config: WalkForwardConfig,
    ) -> list[WalkForwardWindow]:
        """Generate rolling or expanding (anchored) In-Sample / Out-of-Sample windows."""
        total_days = (end_date - start_date).days
        min_required = config.train_period_days + config.test_period_days
        if total_days < min_required:
            raise InvalidWindowSpecError(
                f"Date range ({total_days} days) is shorter than minimum required train + test period ({min_required} days)."
            )

        windows: list[WalkForwardWindow] = []
        window_idx = 0

        current_train_start = start_date

        while True:
            train_end = current_train_start + timedelta(days=config.train_period_days)
            
            # Apply purge buffer if configured
            test_start = train_end + timedelta(days=config.purge_window_days)
            test_end = test_start + timedelta(days=config.test_period_days)

            if test_end > end_date:
                # If remaining window is at least half of test period, use truncated end
                if (end_date - test_start).days >= (config.test_period_days // 2):
                    test_end = end_date
                else:
                    break

            # Calculate embargo boundary
            embargo_days = int(config.test_period_days * float(config.embargo_pct))
            embargo_start = test_end
            embargo_end = test_end + timedelta(days=embargo_days) if embargo_days > 0 else None

            windows.append(
                WalkForwardWindow(
                    window_index=window_idx,
                    train_start=current_train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    purge_start=train_end if config.purge_window_days > 0 else None,
                    purge_end=test_start if config.purge_window_days > 0 else None,
                    embargo_start=embargo_start,
                    embargo_end=embargo_end,
                )
            )
            window_idx += 1

            if test_end >= end_date:
                break

            # Step forward
            if config.window_type == WindowType.rolling:
                current_train_start += timedelta(days=config.step_days)
            else:
                # Expanding / anchored window keeps start_date fixed
                pass

            # In expanding window, we increment train_end by stepping
            if config.window_type == WindowType.expanding:
                train_period_increment = config.step_days * window_idx
                if (start_date + timedelta(days=config.train_period_days + train_period_increment)) >= end_date:
                    break

        return windows

    @staticmethod
    def aggregate_oos_results(
        segment_results: list[WalkForwardSegmentResult],
        initial_capital: float = 100000.0,
    ) -> WalkForwardValidationSummary:
        """Stitches together Out-of-Sample equity curves and computes composite metrics."""
        if not segment_results:
            empty_rep = PerformanceMetricsCalculator._empty_report().to_dict()
            return WalkForwardValidationSummary(
                total_windows=0,
                window_type=WindowType.rolling,
                mean_is_sharpe=0.0,
                mean_oos_sharpe=0.0,
                mean_wfe_ratio=0.0,
                concatenated_oos_metrics=empty_rep,
                concatenated_oos_equity_curve=[],
                window_results=[],
            )

        # Concatenate OOS equity curve with compounding capital
        concatenated_curve: list[dict[str, Any]] = []
        equity_series: list[float] = [initial_capital]
        current_equity = initial_capital

        for seg in segment_results:
            oos_curve = seg.oos_equity_curve
            if len(oos_curve) < 2:
                continue

            seg_init = oos_curve[0]["equity"]
            for pt in oos_curve[1:]:
                # Apply relative return from this segment to compounded running equity
                ret = (pt["equity"] - seg_init) / seg_init if seg_init > 0 else 0.0
                pt_equity = current_equity * (1.0 + ret)
                equity_series.append(pt_equity)
                concatenated_curve.append({
                    "ts": pt["ts"],
                    "equity": round(pt_equity, 2),
                    "window_index": seg.window.window_index,
                })
            # Advance compounded equity
            if oos_curve:
                final_seg_ret = (oos_curve[-1]["equity"] - seg_init) / seg_init if seg_init > 0 else 0.0
                current_equity = current_equity * (1.0 + final_seg_ret)

        comp_metrics = PerformanceMetricsCalculator.calculate(equity_series).to_dict()

        is_sharpes = [r.is_metrics.get("sharpe_ratio", 0.0) for r in segment_results]
        oos_sharpes = [r.oos_metrics.get("sharpe_ratio", 0.0) for r in segment_results]
        wfes = [r.wfe_ratio for r in segment_results]

        mean_is = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0.0
        mean_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0
        mean_wfe = sum(wfes) / len(wfes) if wfes else 0.0

        return WalkForwardValidationSummary(
            total_windows=len(segment_results),
            window_type=WindowType.rolling,
            mean_is_sharpe=round(mean_is, 4),
            mean_oos_sharpe=round(mean_oos, 4),
            mean_wfe_ratio=round(mean_wfe, 4),
            concatenated_oos_metrics=comp_metrics,
            concatenated_oos_equity_curve=concatenated_curve,
            window_results=segment_results,
        )
