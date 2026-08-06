"""Integration tests for Platform Observability REST APIs and Pipeline Operations."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.orchestrator.enums import OrchestratorMode
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.invariants import InvariantValidator
from app.domains.orchestrator.metrics import ContinuousMetricsTracker
from app.domains.orchestrator.pipeline import ExecutionPipelineRunner
from app.domains.orchestrator.session_manager import MarketSessionManager
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.risk.service import RiskService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import FixedClock
from app.domains.trading.models import Portfolio
from app.main import app


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_platform_health_endpoint(client: TestClient):
    resp = client.get("/api/v1/platform/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_status" in data
    assert "subsystems" in data
    assert "database" in data["subsystems"]
    assert "market_data" in data["subsystems"]


def test_platform_status_endpoint(client: TestClient):
    resp = client.get("/api/v1/platform/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "environment" in data
    assert "active_circuit_breakers" in data


def test_platform_runtime_config_get_and_update(client: TestClient):
    # GET
    resp = client.get("/api/v1/platform/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["max_active_orders"] >= 1

    # POST UPDATE
    update_resp = client.post(
        "/api/v1/platform/config",
        json={"max_active_orders": 150, "logging_level": "DEBUG"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["max_active_orders"] == 150
    assert updated["logging_level"] == "DEBUG"


def test_platform_circuit_breakers_and_reset(client: TestClient):
    resp = client.get("/api/v1/platform/circuit-breakers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # Test reset
    reset_resp = client.post("/api/v1/platform/circuit-breakers/market_data/reset")
    assert reset_resp.status_code == 200
    data = reset_resp.json()
    assert data["name"] == "market_data"
    assert data["snapshot"]["state"] == "closed"


def test_platform_telemetry_endpoint(client: TestClient):
    resp = client.get("/api/v1/platform/metrics/telemetry")
    assert resp.status_code == 200
    data = resp.json()
    assert "cycle_latency" in data
    assert "throughput" in data
    assert "resources" in data


def test_end_to_end_pipeline_observability(db: Session, client: TestClient):
    clock = FixedClock(initial_time=datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc))
    session_mgr = MarketSessionManager()
    portfolio_svc = PortfolioConstructionService(clock=clock)
    risk_svc = RiskService(clock=clock)
    event_bus = EventBus()
    metrics_tracker = ContinuousMetricsTracker()
    invariants = InvariantValidator()

    pipeline = ExecutionPipelineRunner(
        clock=clock,
        session_manager=session_mgr,
        portfolio_service=portfolio_svc,
        risk_service=risk_svc,
        event_bus=event_bus,
        metrics_tracker=metrics_tracker,
        invariant_validator=invariants,
    )

    # Setup test portfolio & instrument
    port = Portfolio(
        id=uuid.uuid4(),
        name="Platform Obs Portfolio",
        base_currency="INR",
        cash_balance=Decimal("1000000.00"),
    )
    db.add(port)

    inst = Instrument(
        id=uuid.uuid4(),
        trading_symbol="TCS",
        name="Tata Consultancy Services",
        exchange=Exchange.NSE,
        lot_size=1,
        tick_size=0.05,
        currency="INR",
        is_active=True,
    )
    db.add(inst)
    db.commit()

    sig = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="strat_obs",
        strategy_version="1.0.0",
        symbol="TCS",
        instrument_id=inst.id,
        timestamp=datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc),
        direction=SignalDirection.long,
        signal_type=SignalType.entry_long,
        confidence=0.9,
        target_quantity=Decimal("10.0000"),
        entry_price=Decimal("3450.00"),
        stop_loss=Decimal("3300.00"),
        take_profit=Decimal("3600.00"),
    )

    res = pipeline.run_cycle(
        db=db,
        portfolio_id=port.id,
        mode=OrchestratorMode.paper,
        provided_signals=[sig],
        current_prices={inst.id: Decimal("3450.00")},
    )

    assert res.status.value == "success"
    assert res.orders_submitted_count >= 1

    # Verify Traces via REST endpoint
    traces_resp = client.get("/api/v1/platform/traces")
    assert traces_resp.status_code == 200
    traces = traces_resp.json()
    assert len(traces) > 0
    cycle_trace = next((t for t in traces if t["name"] == "execution_cycle"), None)
    assert cycle_trace is not None
    assert len(cycle_trace["spans"]) >= 6

    # Verify Audit trail via REST endpoint
    audit_resp = client.get("/api/v1/platform/audit")
    assert audit_resp.status_code == 200
    audit_records = audit_resp.json()
    assert len(audit_records) > 0
    actions = [r["action"] for r in audit_records]
    assert "pipeline_started" in actions
    assert "pipeline_completed" in actions

    # Verify Logs via REST endpoint
    logs_resp = client.get("/api/v1/platform/logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert len(logs) > 0
