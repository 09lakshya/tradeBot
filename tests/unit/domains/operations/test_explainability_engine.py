"""Unit tests for Strategy Explainability Engine."""
from __future__ import annotations

from pathlib import Path
from app.domains.operations.explainability_engine import StrategyExplainabilityEngine
from app.domains.operations.models import (
    ExecutionReason,
    PortfolioReason,
    RiskReason,
    SignalReason,
)


def test_record_and_generate_narrative_explanation(tmp_path: Path):
    engine = StrategyExplainabilityEngine(storage_dir=tmp_path)

    sig_r = SignalReason(
        indicators_involved=["RSI", "MACD"],
        indicator_values={"RSI": 32.5, "MACD_hist": 0.45},
        confidence_score=0.88,
        rationale="RSI crossed above 30 while MACD generated bullish crossover",
    )
    risk_r = RiskReason(
        approved=True,
        rules_evaluated=["max_drawdown", "leverage_limit"],
        rationale="Exposure remained below configured limits",
    )
    port_r = PortfolioReason(
        accepted=True,
        position_sizing_selected=4000.0,
        sizing_rationale="volatility targeting",
        allocation_weight=0.04,
    )
    exec_r = ExecutionReason(
        executed=True,
        fill_price=182.50,
        slippage=0.0005,
        commission=1.50,
        rationale="VWAP execution filled",
    )

    exp = engine.record_explanation(
        trade_id="trd_1001",
        strategy_id="trend_v1",
        symbol="AAPL",
        side="BUY",
        signal_reason=sig_r,
        risk_reason=risk_r,
        portfolio_reason=port_r,
        execution_reason=exec_r,
    )

    assert exp.trade_id == "trd_1001"
    assert "RSI crossed above 30" in exp.narrative
    assert "Portfolio accepted allocation of 4.0% capital" in exp.narrative
    assert "Risk engine approved" in exp.narrative

    retrieved = engine.get_explanation("trd_1001")
    assert retrieved is not None
    assert retrieved.symbol == "AAPL"
