"""FastAPI router for Backtest domain endpoints."""
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.backtest.deps import get_backtest_service
from app.domains.backtest.models import Backtest
from app.domains.backtest.reporting import BacktestReportGenerator
from app.domains.backtest.schemas import (
    BacktestCreateRequest,
    BacktestSummaryResponse,
    MonteCarloConfig,
    MonteCarloSimulationResponse,
)
from app.domains.backtest.service import BacktestService

router = APIRouter()


@router.post("", response_model=BacktestSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_and_run_backtest(
    request: BacktestCreateRequest,
    service: BacktestService = Depends(get_backtest_service),
) -> Any:
    """Create and immediately execute a backtest run."""
    bt = service.create_backtest(request)
    try:
        completed_bt = service.run_backtest(bt.id)
        return completed_bt
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest execution failed: {str(e)}",
        )


@router.get("/{backtest_id}", response_model=BacktestSummaryResponse)
def get_backtest(
    backtest_id: uuid.UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> Any:
    """Retrieve full details of a backtest run including results and trades."""
    bt = service.get_backtest(backtest_id)
    if not bt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest {backtest_id} not found.",
        )
    return bt


@router.get("/{backtest_id}/report", response_model=dict[str, Any])
def get_backtest_report(
    backtest_id: uuid.UUID,
    service: BacktestService = Depends(get_backtest_service),
) -> Any:
    """Retrieve structured monthly/yearly return matrices and markdown report."""
    bt = service.get_backtest(backtest_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest not found.")

    if not bt.results:
        raise HTTPException(status_code=400, detail="Backtest has no completed results.")

    primary_res = bt.results[0]
    eq_curve = primary_res.equity_curve or []
    monthly_table = BacktestReportGenerator.generate_monthly_returns_table(eq_curve)
    drawdowns = BacktestReportGenerator.generate_drawdown_table(eq_curve)
    md_report = BacktestReportGenerator.generate_markdown_report(
        backtest_name=bt.name,
        strategy_id=bt.strategy_id,
        metrics=primary_res.metrics,
        config_snapshot=bt.config_snapshot,
        monthly_returns=monthly_table,
        top_drawdowns=drawdowns,
    )

    return {
        "backtest_id": bt.id,
        "name": bt.name,
        "monthly_returns": monthly_table,
        "top_drawdowns": drawdowns,
        "markdown_report": md_report,
    }


@router.post("/{backtest_id}/monte-carlo", response_model=MonteCarloSimulationResponse)
def run_monte_carlo_analysis(
    backtest_id: uuid.UUID,
    config: MonteCarloConfig,
    service: BacktestService = Depends(get_backtest_service),
) -> Any:
    """Run Monte Carlo trade resampling and ruin probability estimation on completed backtest."""
    try:
        mc_result = service.run_monte_carlo(backtest_id, config)
        return MonteCarloSimulationResponse(
            backtest_id=backtest_id,
            iterations=mc_result.iterations,
            random_seed=mc_result.random_seed,
            terminal_equity_quantiles=mc_result.terminal_equity_quantiles,
            max_drawdown_quantiles=mc_result.max_drawdown_quantiles,
            sharpe_quantiles=mc_result.sharpe_quantiles,
            probability_of_ruin=mc_result.probability_of_ruin,
            var_95=mc_result.var_95,
            cvar_95=mc_result.cvar_95,
            simulated_equity_paths=mc_result.sample_equity_paths,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
