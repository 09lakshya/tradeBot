"""Unit tests for the Trading domain REST API endpoints."""
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.models import Instrument
from app.main import create_app


from collections.abc import Iterator
from app.core.db import get_db
from app.domains.trading.deps import get_trading_service
from app.domains.trading.service import TradingService
from app.domains.trading.clock import FixedClock


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_trading_service] = lambda: TradingService(db, FixedClock())
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_trading_api_endpoints_flow(client, db):
    # 1. Setup Instrument
    inst = Instrument(
        trading_symbol="SBIN",
        name="State Bank of India",
        exchange=Exchange.NSE,
        asset_class=AssetClass.equity,
    )
    db.add(inst)
    db.commit()

    # 2. Create Portfolio
    port_resp = client.post(
        "/api/v1/trading/portfolios",
        json={"name": "API Test Port", "initial_capital": "500000.0000"},
    )
    assert port_resp.status_code == 201
    port_data = port_resp.json()
    port_id = port_data["id"]
    assert float(port_data["cash_balance"]) == 500000.0

    # 3. Submit Order with Decision record and Idempotency key
    order_resp = client.post(
        "/api/v1/trading/orders",
        json={
            "portfolio_id": port_id,
            "instrument_id": str(inst.id),
            "side": "buy",
            "order_type": "limit",
            "quantity": "50.0000",
            "limit_price": "600.0000",
            "idempotency_key": "api-idem-key-1",
            "decision": {
                "model_confidence": "0.92",
                "entry_reason": "Quarterly earnings beat",
                "summary": "High conviction buy signal",
            },
        },
    )
    assert order_resp.status_code == 201
    order_data = order_resp.json()
    order_id = order_data["id"]
    assert order_data["status"] == "pending"
    assert order_data["decision"]["entry_reason"] == "Quarterly earnings beat"

    # 4. Duplicate Idempotency Key returns 409 Conflict
    dup_resp = client.post(
        "/api/v1/trading/orders",
        json={
            "portfolio_id": port_id,
            "instrument_id": str(inst.id),
            "side": "buy",
            "order_type": "limit",
            "quantity": "50.0000",
            "limit_price": "600.0000",
            "idempotency_key": "api-idem-key-1",
        },
    )
    assert dup_resp.status_code == 409

    # 5. Execute Order Fill
    exec_resp = client.post(
        f"/api/v1/trading/orders/{order_id}/execute",
        json={"market_price": "598.0000", "exchange": "NSE"},
    )
    assert exec_resp.status_code == 200
    fill_data = exec_resp.json()
    assert float(fill_data["price"]) == 598.0
    assert float(fill_data["quantity"]) == 50.0

    # 6. Verify Position Endpoint
    pos_resp = client.get(f"/api/v1/trading/positions?portfolio_id={port_id}")
    assert pos_resp.status_code == 200
    positions = pos_resp.json()
    assert len(positions) == 1
    assert float(positions[0]["quantity"]) == 50.0

    # 7. Verify Portfolio Summary Endpoint
    summary_resp = client.get(f"/api/v1/trading/portfolios/{port_id}/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["open_positions_count"] == 1
    assert float(summary["open_positions_market_value"]) > 0

    # 8. Verify Ledger Reconciliation Endpoint
    rec_resp = client.post(f"/api/v1/trading/portfolios/{port_id}/reconcile")
    assert rec_resp.status_code == 200
    assert rec_resp.json()["reconciled"] is True
