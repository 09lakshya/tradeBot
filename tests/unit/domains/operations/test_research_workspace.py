"""Unit tests for Research Workspace & Experiment Engine."""
from __future__ import annotations

from pathlib import Path
from app.domains.operations.models import ExperimentConfig, ExperimentStatus
from app.domains.operations.research_workspace import ResearchWorkspaceEngine


def test_research_experiment_lifecycle(tmp_path: Path):
    workspace = ResearchWorkspaceEngine(exp_dir=tmp_path)
    cfg = ExperimentConfig(
        strategy_id="trend_v1",
        symbols=["AAPL", "MSFT"],
        start_date="2026-01-01",
        end_date="2026-06-01",
        parameters={"rsi_period": 14},
    )

    exp = workspace.create_experiment(
        name="RSI Parameter Sweep",
        experiment_type="parameter_comparison",
        config=cfg,
        description="Testing RSI periods 10 vs 14 vs 20",
    )
    assert exp.status == ExperimentStatus.pending

    executed_exp = workspace.run_experiment(exp.experiment_id)
    assert executed_exp.status == ExperimentStatus.completed
    assert executed_exp.baseline_results is not None
    assert "variant_A_fast_rsi" in executed_exp.variant_results

    annotated = workspace.add_note_to_experiment(exp.experiment_id, "Variant A fast RSI yielded higher Sharpe ratio.")
    assert len(annotated.notes) == 1
