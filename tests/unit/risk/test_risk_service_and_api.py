"""Unit tests for RiskService and FastAPI REST endpoints."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.domains.market_data.models import Instrument
from app.domains.risk.deps import get_clock, get_risk_service
from app.domains.risk.enums import RiskDecision, ScopeType
from app.domains.risk.models import RiskLimit
from app.domains.risk.schemas import RiskLimitUpdate
from app.domains.risk.service import RiskService
from app.domains.platform.models import User
from app.domains.trading.clock import FixedClock
from app.domains.trading.enums import OrderSide, OrderType, ProductType, TimeInForce
from app.domains.trading.models import Order, Portfolio
from app.main import app


@pytest.fixture
def mem_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def fixed_clock():
    return FixedClock(datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def test_client(mem_db, fixed_clock):
    def _override_get_db():
        yield mem_db

    def _override_get_clock():
        return fixed_clock

    def _override_get_risk_service():
        return RiskService(clock=fixed_clock)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = _override_get_clock
    app.dependency_overrides[get_risk_service] = _override_get_risk_service

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def setup_portfolio(mem_db):
    user = User(email="risk@tradebot.local", hashed_password="fakehashpassword")
    mem_db.add(user)
    mem_db.flush()

    portfolio = Portfolio(
        user_id=user.id,
        name="Risk Test Portfolio",
        cash_balance=Decimal("100000.0000"),
        reserved_cash=Decimal("0.0000"),
    )
    mem_db.add(portfolio)

    instrument = Instrument(
        trading_symbol="INFY",
        name="Infosys Limited",
        exchange="NSE",
        asset_class="equity",
        is_active=True,
    )
    mem_db.add(instrument)
    mem_db.commit()
    return portfolio, instrument


def test_get_and_update_risk_limits(mem_db, setup_portfolio):
    portfolio, _ = setup_portfolio
    clock = FixedClock(datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc))
    service = RiskService(clock=clock)

    # Auto-creates default limits
    limits = service.get_or_create_limits(mem_db, portfolio.id)
    assert limits.max_daily_loss_pct == Decimal("0.5000")
    assert limits.max_drawdown_pct == Decimal("0.5000")

    # Update limits
    updates = RiskLimitUpdate(
        max_daily_loss_pct=Decimal("0.0300"),
        max_drawdown_pct=Decimal("0.1000"),
        max_open_positions=5,
    )
    updated = service.update_limits(mem_db, portfolio.id, updates)
    assert updated.max_daily_loss_pct == Decimal("0.0300")
    assert updated.max_drawdown_pct == Decimal("0.1000")
    assert updated.max_open_positions == 5


def test_risk_status_summary(mem_db, setup_portfolio):
    portfolio, _ = setup_portfolio
    clock = FixedClock(datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc))
    service = RiskService(clock=clock)

    summary = service.get_risk_status(mem_db, portfolio.id)
    assert summary.portfolio_id == portfolio.id
    assert summary.current_equity == Decimal("100000.0000")
    assert summary.kill_switch_active is False
    assert summary.active_circuit_breakers_count == 0


def test_risk_api_endpoints(test_client, setup_portfolio):
    portfolio, _ = setup_portfolio
    port_id = str(portfolio.id)

    # 1. GET /risk/limits/{portfolio_id}
    resp = test_client.get(f"/api/v1/risk/limits/{port_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_id"] == port_id
    assert float(data["max_daily_loss_pct"]) == 0.5

    # 2. PUT /risk/limits/{portfolio_id}
    put_resp = test_client.put(
        f"/api/v1/risk/limits/{port_id}",
        json={"max_daily_loss_pct": "0.0400", "max_open_positions": 8},
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert float(put_data["max_daily_loss_pct"]) == 0.04
    assert put_data["max_open_positions"] == 8

    # 3. GET /risk/status/{portfolio_id}
    status_resp = test_client.get(f"/api/v1/risk/status/{port_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["portfolio_id"] == port_id
    assert status_data["kill_switch_active"] is False

    # 4. POST /risk/kill-switch/{portfolio_id}/trip
    trip_resp = test_client.post(
        f"/api/v1/risk/kill-switch/{port_id}/trip",
        json={"reason": "Suspected market volatility breach", "activated_by": "api_test"},
    )
    assert trip_resp.status_code == 200
    trip_data = trip_resp.json()
    assert trip_data["is_active"] is True
    assert trip_data["reason"] == "Suspected market volatility breach"

    # Status now reports kill switch active
    status_resp_after = test_client.get(f"/api/v1/risk/status/{port_id}")
    assert status_resp_after.json()["kill_switch_active"] is True

    # 5. POST /risk/kill-switch/{portfolio_id}/reset
    reset_resp = test_client.post(
        f"/api/v1/risk/kill-switch/{port_id}/reset",
        json={"reset_reason": "Market conditions stabilized", "reset_by": "admin"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["is_active"] is False
