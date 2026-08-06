"""Integration tests for the Execution Orchestrator and Paper Trading Pipeline."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.domains.market_data.enums import AssetClass, Exchange, InstrumentType
from app.domains.market_data.models import Instrument
from app.domains.orchestrator.deps import get_orchestrator_service
from app.domains.orchestrator.enums import CycleStatus, OrchestratorMode
from app.domains.orchestrator.event_bus import EventBus
from app.domains.orchestrator.schemas import ExecutionCycleRequest
from app.domains.orchestrator.service import ExecutionOrchestratorService
from app.domains.orchestrator.session_manager import MarketSessionManager
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.risk.service import RiskService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import FixedClock
from app.domains.trading.models import Order, Portfolio, Position
from app.main import app


@pytest.fixture
def integration_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_setup(integration_db):
    clock = FixedClock(datetime(2025, 4, 15, 10, 0, 0, tzinfo=timezone.utc))
    event_bus = EventBus()
    session_mgr = MarketSessionManager()
    risk_service = RiskService(clock=clock)
    portfolio_service = PortfolioConstructionService(clock=clock)

    orchestrator = ExecutionOrchestratorService(
        clock=clock,
        session_manager=session_mgr,
        event_bus=event_bus,
        risk_service=risk_service,
        portfolio_service=portfolio_service,
    )

    # Seed Portfolio
    pid = uuid.uuid4()
    p = Portfolio(
        id=pid,
        name="Production Paper Portfolio",
        initial_capital=Decimal("1000000.00"),
        cash_balance=Decimal("1000000.00"),
        reserved_cash=Decimal("0.00"),
        base_currency="INR",
        mode="paper",
    )
    integration_db.add(p)

    # Seed Instruments
    inst1 = Instrument(
        id=uuid.uuid4(),
        trading_symbol="RELIANCE",
        exchange=Exchange.NSE,
        name="Reliance Industries Ltd",
        asset_class=AssetClass.equity,
        instrument_type=InstrumentType.eq,
        lot_size=1,
        tick_size=Decimal("0.05"),
        is_active=True,
    )
    inst2 = Instrument(
        id=uuid.uuid4(),
        trading_symbol="INFY",
        exchange=Exchange.NSE,
        name="Infosys Ltd",
        asset_class=AssetClass.equity,
        instrument_type=InstrumentType.eq,
        lot_size=1,
        tick_size=Decimal("0.05"),
        is_active=True,
    )
    integration_db.add_all([inst1, inst2])
    integration_db.commit()

    return {
        "clock": clock,
        "event_bus": event_bus,
        "service": orchestrator,
        "portfolio": p,
        "inst1": inst1,
        "inst2": inst2,
    }


def test_full_pipeline_execution_cycle(integration_db, test_setup):
    service = test_setup["service"]
    portfolio = test_setup["portfolio"]
    inst1 = test_setup["inst1"]
    inst2 = test_setup["inst2"]
    now = test_setup["clock"].now()

    # Generate signals
    sig1 = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="trend_momentum_v1",
        instrument_id=inst1.id,
        symbol=inst1.trading_symbol,
        timestamp=now,
        direction=SignalDirection.long,
        signal_type=SignalType.entry_long,
        confidence=0.85,
        target_quantity=Decimal("10.00"),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2450.00"),
        take_profit=Decimal("2550.00"),
    )
    sig2 = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="mean_reversion_v1",
        instrument_id=inst2.id,
        symbol=inst2.trading_symbol,
        timestamp=now,
        direction=SignalDirection.long,
        signal_type=SignalType.entry_long,
        confidence=0.75,
        target_quantity=Decimal("15.00"),
        entry_price=Decimal("1450.00"),
        stop_loss=Decimal("1420.00"),
        take_profit=Decimal("1500.00"),
    )

    req = ExecutionCycleRequest(
        portfolio_id=portfolio.id,
        mode=OrchestratorMode.paper,
        enforce_market_hours=False,
    )

    res = service.execute_cycle(
        db=integration_db,
        req=req,
        provided_signals=[sig1, sig2],
        current_prices={inst1.id: Decimal("2500.00"), inst2.id: Decimal("1450.00")},
    )

    assert res.status == CycleStatus.success
    assert res.signals_evaluated_count == 2
    assert res.candidate_orders_count == 2
    assert res.orders_submitted_count == 2
    assert res.orders_filled_count == 2
    assert res.duration_ms > 0.0

    # Verify orders in DB
    orders = integration_db.query(Order).filter(Order.portfolio_id == portfolio.id).all()
    assert len(orders) == 2

    # Verify positions in DB
    positions = integration_db.query(Position).filter(Position.portfolio_id == portfolio.id).all()
    assert len(positions) == 2


def test_orchestrator_api_routes(integration_db, test_setup):
    service = test_setup["service"]
    portfolio = test_setup["portfolio"]

    def override_get_db():
        yield integration_db

    def override_get_service():
        return service

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_orchestrator_service] = override_get_service

    client = TestClient(app)

    # 1. Pipeline Status
    resp = client.get("/api/v1/orchestrator/status")
    assert resp.status_code == 200
    assert resp.json()["is_running"] is True

    # 2. Session Status
    resp = client.get("/api/v1/orchestrator/session")
    assert resp.status_code == 200
    assert "session_state" in resp.json()

    # 3. Health Diagnostics
    resp = client.get("/api/v1/orchestrator/health")
    assert resp.status_code == 200
    assert "subsystems" in resp.json()

    # 4. Continuous Metrics
    resp = client.get(f"/api/v1/orchestrator/metrics/{portfolio.id}")
    assert resp.status_code == 200
    assert "total_equity" in resp.json()

    # 5. Invariants Check
    resp = client.post(f"/api/v1/orchestrator/invariants/verify/{portfolio.id}")
    assert resp.status_code == 200
    assert resp.json()["all_passed"] is True

    app.dependency_overrides.clear()
