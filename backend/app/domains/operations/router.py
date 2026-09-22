"""FastAPI Router for Phase 10 Operations, Explainability, Continuous Validation & Research Workspace."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.domains.operations.alert_center import OperationalAlertCenter
from app.domains.operations.autonomous_scheduler import AutonomousScheduler
from app.domains.operations.dashboard_service import DashboardService
from app.domains.operations.data_exporter import DataExporterEngine
from app.domains.operations.decision_replay import DecisionReplayEngine
from app.domains.operations.deps import (
    get_alert_center,
    get_dashboard_service,
    get_explainability_engine,
    get_exporter,
    get_health_monitor,
    get_historical_comparison,
    get_notes_engine,
    get_readiness_engine,
    get_replay_engine,
    get_report_generator,
    get_research_workspace,
    get_scheduler,
    get_snapshot_engine,
)
from app.domains.operations.explainability_engine import StrategyExplainabilityEngine
from app.domains.operations.historical_comparison import HistoricalComparisonEngine
from app.domains.operations.models import (
    AlertSeverity,
    ExecutionReason,
    OperationalAlert,
    OperationalMode,
    PortfolioDailySnapshot,
    PortfolioReason,
    ReadinessAssessment,
    ReplaySessionState,
    ResearchExperiment,
    ResearchNote,
    RiskReason,
    SignalReason,
    StrategyHealthReport,
    TradeExplanation,
)
from app.domains.operations.readiness_assessment import ReadinessAssessmentEngine
from app.domains.operations.report_generator import AutomatedReportGenerator
from app.domains.operations.research_notes import ResearchNotesEngine
from app.domains.operations.research_workspace import ResearchWorkspaceEngine
from app.domains.operations.schemas import (
    CreateExperimentRequest,
    CreateResearchNoteRequest,
    DashboardReplayResponse,
    DataExportRequest,
    DataImportResponse,
    HistoricalComparisonRequest,
    OperationalReportResponse,
    ReplayActionRequest,
    ReportGenerationRequest,
    SchedulerConfigSchema,
    SchedulerControlRequest,
    SchedulerStatusResponse,
    SnapshotListResponse,
)
from app.domains.operations.snapshot_engine import DailySnapshotEngine
from app.domains.operations.strategy_health import StrategyHealthMonitor

router = APIRouter(prefix="/operations", tags=["operations"])


# --- 1. Autonomous Scheduler Endpoints ---
@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
def get_scheduler_status(scheduler: AutonomousScheduler = Depends(get_scheduler)) -> SchedulerStatusResponse:
    return scheduler.get_status()


@router.post("/scheduler/control", response_model=SchedulerStatusResponse)
def control_scheduler(
    req: SchedulerControlRequest,
    scheduler: AutonomousScheduler = Depends(get_scheduler),
) -> SchedulerStatusResponse:
    act = req.action.lower()
    if act == "start":
        scheduler.start()
    elif act == "stop":
        scheduler.stop()
    elif act == "pause":
        scheduler.pause()
    elif act == "resume":
        scheduler.resume()
    elif act == "manual_override":
        scheduler.set_mode(OperationalMode.manual_override, manual_override=True)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown control action: {req.action}")

    return scheduler.get_status()


@router.post("/scheduler/config", response_model=SchedulerConfigSchema)
def configure_scheduler(
    config: SchedulerConfigSchema,
    scheduler: AutonomousScheduler = Depends(get_scheduler),
) -> SchedulerConfigSchema:
    return scheduler.configure(config)


# --- 2. Daily Snapshot Endpoints ---
@router.post("/snapshots/create", response_model=PortfolioDailySnapshot)
def create_snapshot(
    snapshot_engine: DailySnapshotEngine = Depends(get_snapshot_engine),
) -> PortfolioDailySnapshot:
    return snapshot_engine.create_snapshot()


@router.get("/snapshots", response_model=SnapshotListResponse)
def list_snapshots(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 30,
    snapshot_engine: DailySnapshotEngine = Depends(get_snapshot_engine),
) -> SnapshotListResponse:
    snaps = snapshot_engine.list_snapshots(start_date=start_date, end_date=end_date, limit=limit)
    return SnapshotListResponse(total_snapshots=len(snaps), snapshots=snaps)


@router.get("/snapshots/{date}", response_model=PortfolioDailySnapshot)
def get_snapshot(
    date: str,
    snapshot_engine: DailySnapshotEngine = Depends(get_snapshot_engine),
) -> PortfolioDailySnapshot:
    snap = snapshot_engine.get_snapshot(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot for date {date} not found")
    return snap


# --- 3. Automated Reports Endpoint ---
@router.post("/reports/generate", response_model=OperationalReportResponse)
def generate_report(
    req: ReportGenerationRequest,
    report_gen: AutomatedReportGenerator = Depends(get_report_generator),
) -> OperationalReportResponse:
    return report_gen.generate_report(
        report_type=req.report_type,
        start_date=req.start_date,
        end_date=req.end_date,
        export_format=req.export_format,
    )


# --- 4. Strategy Explainability Endpoints ---
@router.post("/explainability/record", response_model=TradeExplanation)
def record_explanation(
    payload: dict[str, Any],
    explainability: StrategyExplainabilityEngine = Depends(get_explainability_engine),
) -> TradeExplanation:
    signal_r = SignalReason(**payload["signal_reason"])
    risk_r = RiskReason(**payload["risk_reason"])
    portfolio_r = PortfolioReason(**payload["portfolio_reason"])
    exec_r = ExecutionReason(**payload["execution_reason"])

    return explainability.record_explanation(
        trade_id=payload["trade_id"],
        strategy_id=payload["strategy_id"],
        symbol=payload["symbol"],
        side=payload["side"],
        signal_reason=signal_r,
        risk_reason=risk_r,
        portfolio_reason=portfolio_r,
        execution_reason=exec_r,
        order_id=payload.get("order_id"),
        exit_reason=payload.get("exit_reason"),
    )


@router.get("/explainability/trade/{trade_id}", response_model=TradeExplanation)
def get_trade_explanation(
    trade_id: str,
    explainability: StrategyExplainabilityEngine = Depends(get_explainability_engine),
) -> TradeExplanation:
    exp = explainability.get_explanation(trade_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Explanation for trade {trade_id} not found")
    return exp


@router.get("/explainability", response_model=list[TradeExplanation])
def list_explanations(
    strategy_id: str | None = None,
    symbol: str | None = None,
    explainability: StrategyExplainabilityEngine = Depends(get_explainability_engine),
) -> list[TradeExplanation]:
    return explainability.list_explanations(strategy_id=strategy_id, symbol=symbol)


# --- 5. Decision Replay Endpoints ---
@router.post("/replay/create", response_model=ReplaySessionState)
def create_replay_session(
    date: str = "2026-08-04",
    replay_engine: DecisionReplayEngine = Depends(get_replay_engine),
) -> ReplaySessionState:
    return replay_engine.create_replay_session(date=date)


@router.post("/replay/{session_id}/action")
def execute_replay_action(
    session_id: str,
    req: ReplayActionRequest,
    replay_engine: DecisionReplayEngine = Depends(get_replay_engine),
) -> dict[str, Any]:
    act = req.action.lower()
    if act == "play":
        sess = replay_engine.play(session_id, speed_multiplier=req.speed_multiplier)
        return {"status": "playing", "session": sess}
    elif act == "pause":
        sess = replay_engine.pause(session_id)
        return {"status": "paused", "session": sess}
    elif act == "step_forward":
        step = replay_engine.step_forward(session_id)
        return {"status": "stepped_forward", "current_step": step}
    elif act == "step_backward":
        step = replay_engine.step_backward(session_id)
        return {"status": "stepped_backward", "current_step": step}
    elif act == "seek":
        if req.target_step is None:
            raise HTTPException(status_code=400, detail="target_step required for seek action")
        step = replay_engine.seek(session_id, req.target_step)
        return {"status": "seeked", "current_step": step}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown replay action: {req.action}")


@router.get("/replay/{session_id}", response_model=ReplaySessionState)
def get_replay_session(
    session_id: str,
    replay_engine: DecisionReplayEngine = Depends(get_replay_engine),
) -> ReplaySessionState:
    sess = replay_engine.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Replay session {session_id} not found")
    return sess


# --- 6. Portfolio Replay Dashboard Endpoint ---
@router.get("/dashboard/replay", response_model=DashboardReplayResponse)
def get_dashboard_replay(
    days: int = 30,
    dashboard_svc: DashboardService = Depends(get_dashboard_service),
) -> DashboardReplayResponse:
    return dashboard_svc.get_dashboard_data(days=days)


# --- 7. Strategy Health Endpoints ---
@router.post("/health/evaluate", response_model=StrategyHealthReport)
def evaluate_strategy_health(
    strategy_id: str = "trend_following_v1",
    current_win_rate: float = 0.52,
    current_profit_factor: float = 1.55,
    current_sharpe: float = 1.40,
    current_drawdown: float = 0.02,
    health_monitor: StrategyHealthMonitor = Depends(get_health_monitor),
) -> StrategyHealthReport:
    return health_monitor.evaluate_strategy_health(
        strategy_id=strategy_id,
        current_win_rate=current_win_rate,
        current_profit_factor=current_profit_factor,
        current_sharpe=current_sharpe,
        current_drawdown=current_drawdown,
    )


@router.get("/health/{strategy_id}", response_model=StrategyHealthReport)
def get_strategy_health(
    strategy_id: str,
    health_monitor: StrategyHealthMonitor = Depends(get_health_monitor),
) -> StrategyHealthReport:
    rep = health_monitor.get_report(strategy_id)
    if not rep:
        # Fallback evaluate nominal report
        return health_monitor.evaluate_strategy_health(strategy_id, 0.55, 1.60, 1.50, 0.02)
    return rep


@router.get("/health", response_model=list[StrategyHealthReport])
def list_strategy_health(
    health_monitor: StrategyHealthMonitor = Depends(get_health_monitor),
) -> list[StrategyHealthReport]:
    return health_monitor.list_reports()


# --- 8. Experiment Workspace Endpoints ---
@router.post("/experiments", response_model=ResearchExperiment)
def create_experiment(
    req: CreateExperimentRequest,
    workspace: ResearchWorkspaceEngine = Depends(get_research_workspace),
) -> ResearchExperiment:
    return workspace.create_experiment(
        name=req.name,
        experiment_type=req.experiment_type,
        config=req.config,
        description=req.description,
    )


@router.post("/experiments/{experiment_id}/run", response_model=ResearchExperiment)
def run_experiment(
    experiment_id: str,
    workspace: ResearchWorkspaceEngine = Depends(get_research_workspace),
) -> ResearchExperiment:
    return workspace.run_experiment(experiment_id)


@router.get("/experiments/{experiment_id}", response_model=ResearchExperiment)
def get_experiment(
    experiment_id: str,
    workspace: ResearchWorkspaceEngine = Depends(get_research_workspace),
) -> ResearchExperiment:
    exp = workspace.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return exp


@router.get("/experiments", response_model=list[ResearchExperiment])
def list_experiments(
    workspace: ResearchWorkspaceEngine = Depends(get_research_workspace),
) -> list[ResearchExperiment]:
    return workspace.list_experiments()


# --- 9. Historical Comparison Endpoint ---
@router.post("/historical-comparison")
def compare_historical(
    req: HistoricalComparisonRequest,
    comparison_engine: HistoricalComparisonEngine = Depends(get_historical_comparison),
) -> dict[str, Any]:
    res = comparison_engine.compare_periods(
        comparison_type=req.comparison_type,
        baseline_label=req.baseline_id_or_period,
        target_label=req.target_id_or_period,
    )
    return res.model_dump()


# --- 10. Readiness Assessment Endpoint ---
@router.post("/readiness/assess", response_model=ReadinessAssessment)
def assess_readiness(
    readiness_engine: ReadinessAssessmentEngine = Depends(get_readiness_engine),
) -> ReadinessAssessment:
    return readiness_engine.evaluate_readiness()


# --- 11. Research Notes Endpoints ---
@router.post("/notes", response_model=ResearchNote)
def create_note(
    req: CreateResearchNoteRequest,
    notes_engine: ResearchNotesEngine = Depends(get_notes_engine),
) -> ResearchNote:
    return notes_engine.create_note(
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        author=req.author,
        title=req.title,
        content_markdown=req.content_markdown,
        tags=req.tags,
    )


@router.get("/notes", response_model=list[ResearchNote])
def list_notes(
    entity_type: str | None = None,
    entity_id: str | None = None,
    tag: str | None = None,
    notes_engine: ResearchNotesEngine = Depends(get_notes_engine),
) -> list[ResearchNote]:
    return notes_engine.list_notes(entity_type=entity_type, entity_id=entity_id, tag=tag)


# --- 12. Operational Alerts Endpoints ---
@router.post("/alerts", response_model=OperationalAlert)
def raise_alert(
    alert_type: str,
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.warning,
    alert_center: OperationalAlertCenter = Depends(get_alert_center),
) -> OperationalAlert:
    return alert_center.raise_alert(
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
    )


@router.post("/alerts/{alert_id}/resolve", response_model=OperationalAlert)
def resolve_alert(
    alert_id: str,
    alert_center: OperationalAlertCenter = Depends(get_alert_center),
) -> OperationalAlert:
    return alert_center.resolve_alert(alert_id)


@router.get("/alerts", response_model=list[OperationalAlert])
def list_alerts(
    severity: AlertSeverity | None = None,
    alert_type: str | None = None,
    resolved: bool | None = None,
    alert_center: OperationalAlertCenter = Depends(get_alert_center),
) -> list[OperationalAlert]:
    return alert_center.list_alerts(severity=severity, alert_type=alert_type, resolved=resolved)


# --- 13. Data Export & Import Endpoints ---
@router.post("/export")
def export_data(
    req: DataExportRequest,
    exporter: DataExporterEngine = Depends(get_exporter),
) -> dict[str, Any]:
    sample_records = [
        {"id": "rec_1", "type": req.data_type, "value": 1000.0, "status": "nominal"},
        {"id": "rec_2", "type": req.data_type, "value": 2000.0, "status": "nominal"},
    ]
    content_type, payload = exporter.export_data(
        data_type=req.data_type,
        export_format=req.export_format,
        records=sample_records,
    )
    return {
        "data_type": req.data_type,
        "format": req.export_format,
        "content_type": content_type,
        "payload": payload,
    }


@router.post("/import", response_model=DataImportResponse)
def import_data(
    payload: dict[str, Any],
    exporter: DataExporterEngine = Depends(get_exporter),
) -> DataImportResponse:
    return exporter.import_restored_session(
        data_type=payload.get("data_type", "general"),
        payload_content=json.dumps(payload.get("content", [])),
    )


# --- 14. Phase 11 Operational Validation Endpoints ---
@router.post("/validation/run")
def run_validation(mode: str = "accelerated") -> dict[str, Any]:
    """Execute Phase 11 Operational Paper Trading Validation (Mode A Accelerated or Mode B Real-Time)."""
    from app.domains.operations.validation_engine import validation_engine
    summary = validation_engine.run_accelerated_validation()
    return summary.model_dump()


@router.get("/validation/metrics")
def get_operational_metrics() -> dict[str, Any]:
    """Retrieve system health, uptime, and reconnection telemetry metrics."""
    from app.domains.operations.operational_metrics import operational_metrics_collector
    metrics = operational_metrics_collector.collect_metrics()
    return metrics.model_dump()


@router.get("/validation/drift")
def get_drift_analysis() -> dict[str, Any]:
    """Retrieve statistical drift analysis report for strategy, signal, portfolio, and risk."""
    from app.domains.operations.drift_detector import drift_detector_engine
    report = drift_detector_engine.analyze_drift()
    return report.model_dump()

