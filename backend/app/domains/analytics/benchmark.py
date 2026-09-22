"""Benchmark Comparison Engine — Compare portfolio performance against market indices."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.analytics.models import EquitySnapshot
from app.domains.analytics.schemas import BenchmarkComparisonResponse
from app.domains.metrics.calculator import PerformanceMetricsCalculator
from app.domains.platform.logging import get_structured_logger

log = get_structured_logger(__name__)


class BenchmarkComparisonService:
    """Compares portfolio performance against user-provided benchmark series."""

    def compare_against_benchmark(
        self,
        db: Session,
        portfolio_id: uuid.UUID,
        benchmark_series: list[float],
        benchmark_name: str = "nifty_50",
    ) -> BenchmarkComparisonResponse:
        """Compare portfolio equity curve against a benchmark index.

        Args:
            db: Database session.
            portfolio_id: Portfolio to compare.
            benchmark_series: Daily closing values of the benchmark index aligned with equity snapshots.
            benchmark_name: Human-readable benchmark name.

        Returns:
            BenchmarkComparisonResponse with excess return, alpha, beta, tracking error, etc.
        """
        # Build portfolio equity series
        stmt = (
            select(EquitySnapshot.net_equity)
            .where(EquitySnapshot.portfolio_id == portfolio_id)
            .order_by(EquitySnapshot.timestamp)
        )
        portfolio_series = [float(v) for v in db.execute(stmt).scalars().all()]

        if len(portfolio_series) < 2 or len(benchmark_series) < 2:
            return BenchmarkComparisonResponse(
                portfolio_id=portfolio_id,
                benchmark_name=benchmark_name,
            )

        # Align lengths (use shorter of the two)
        min_len = min(len(portfolio_series), len(benchmark_series))
        portfolio_series = portfolio_series[:min_len]
        benchmark_series = benchmark_series[:min_len]

        # Use PerformanceMetricsCalculator with benchmark
        report = PerformanceMetricsCalculator.calculate(
            equity_series=portfolio_series,
            benchmark_series=benchmark_series,
        )

        portfolio_return = report.total_return_pct
        benchmark_return = report.benchmark_return_pct or 0.0
        excess_return = portfolio_return - benchmark_return

        # Relative max drawdown
        port_dd = report.max_drawdown_pct
        bench_report = PerformanceMetricsCalculator.calculate(equity_series=benchmark_series)
        bench_dd = bench_report.max_drawdown_pct
        relative_dd = port_dd - bench_dd

        return BenchmarkComparisonResponse(
            portfolio_id=portfolio_id,
            benchmark_name=benchmark_name,
            portfolio_return_pct=round(portfolio_return, 4),
            benchmark_return_pct=round(benchmark_return, 4),
            excess_return_pct=round(excess_return, 4),
            tracking_error=round(report.tracking_error or 0.0, 4),
            information_ratio=round(report.information_ratio or 0.0, 4),
            alpha=round(report.alpha or 0.0, 4),
            beta=round(report.beta or 0.0, 4),
            relative_max_drawdown_pct=round(relative_dd, 4),
        )
