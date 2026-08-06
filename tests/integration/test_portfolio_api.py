"""Integration tests for Portfolio Construction REST API endpoints."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.trading.models import Portfolio
from app.main import app


@pytest.fixture
def api_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        # Pre-seed DB
        session = SessionLocal()
        portfolio_id = uuid.uuid4()
        port = Portfolio(
            id=portfolio_id,
            name="API Test Portfolio",
            base_currency="INR",
            initial_capital=Decimal("1000000.00"),
            cash_balance=Decimal("1000000.00"),
            reserved_cash=Decimal("0.00"),
        )
        session.add(port)

        inst_id = uuid.uuid4()
        inst = Instrument(
            id=inst_id,
            trading_symbol="INFY",
            name="Infosys Limited",
            exchange=Exchange.NSE,
            lot_size=1,
        )
        session.add(inst)
        session.commit()
        session.close()

        yield client, portfolio_id, inst_id

    app.dependency_overrides.clear()


def test_get_status_and_policies(api_client):
    client, _, _ = api_client
    resp = client.get("/api/v1/portfolio-construction/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert "available_policies" in data

    resp_pol = client.get("/api/v1/portfolio-construction/policies")
    assert resp_pol.status_code == 200
    assert "allocation_policies" in resp_pol.json()


def test_evaluate_and_explain_api(api_client):
    client, portfolio_id, inst_id = api_client
    now = datetime.now(timezone.utc).isoformat()

    sig_payload = {
        "signal_id": str(uuid.uuid4()),
        "strategy_id": "trend_macd",
        "instrument_id": str(inst_id),
        "symbol": "INFY",
        "timestamp": now,
        "signal_type": "entry_long",
        "direction": "long",
        "confidence": 0.90,
        "entry_price": "1600.00",
        "stop_loss": "1550.00",
        "take_profit": "1700.00",
    }

    eval_payload = {
        "portfolio_id": str(portfolio_id),
        "signals": [sig_payload],
        "current_prices": {str(inst_id): "1600.00"},
    }

    resp = client.post("/api/v1/portfolio-construction/evaluate", json=eval_payload)
    assert resp.status_code == 200
    plan_data = resp.json()
    assert plan_data["total_candidates"] == 1
    cand = plan_data["candidate_orders"][0]
    candidate_id = cand["candidate_id"]

    # Test explainability endpoint
    resp_exp = client.get(f"/api/v1/portfolio-construction/explain/{candidate_id}")
    assert resp_exp.status_code == 200
    exp_data = resp_exp.json()
    assert exp_data["symbol"] == "INFY"
    assert exp_data["side"] == "buy"
    assert "explainability_trace" in exp_data

    # Test metrics endpoint
    resp_met = client.get("/api/v1/portfolio-construction/metrics")
    assert resp_met.status_code == 200
    metrics = resp_met.json()
    assert metrics["total_plans_executed"] >= 1
