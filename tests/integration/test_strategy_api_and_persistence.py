"""Integration tests for Strategy Engine REST API and Database Persistence."""
from collections.abc import Iterator
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.strategies.enums import StrategyCategory, StrategyStatus
from app.domains.strategies.models import StrategyDefinition, StrategyParameterSnapshot
from app.domains.strategies.service import StrategyService
from app.main import create_app
import app.domains.strategies.builtin  # Load strategies


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestStrategyAPIAndPersistence:
    """Integration test suite for strategy REST endpoints and audit trail persistence."""

    def test_list_strategies_endpoint(self, client: TestClient, db: Session):
        response = client.get("/api/v1/strategies")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 21

        ids = [item["strategy_id"] for item in data]
        assert "ema_crossover" in ids
        assert "rsi_momentum" in ids
        assert "bollinger_mean_reversion" in ids

    def test_get_strategy_parameters(self, client: TestClient, db: Session):
        response = client.get("/api/v1/strategies/ema_crossover/parameters")
        assert response.status_code == 200
        data = response.json()
        assert data["strategy_id"] == "ema_crossover"
        assert "fast_period" in data["default_parameters"]
        assert "parameter_schema" in data

    def test_validate_parameters_endpoint(self, client: TestClient, db: Session):
        response = client.post(
            "/api/v1/strategies/rsi_momentum/validate",
            json={"parameters": {"period": 14, "oversold_threshold": 25.0}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True

    def test_create_and_list_snapshots(self, db: Session):
        service = StrategyService(db)
        snapshot = service.create_parameter_snapshot(
            strategy_id="bollinger_mean_reversion",
            parameters={"period": 25, "num_std": 2.5},
            description="High volatility parameter tuning",
            created_by="lead_quant",
        )
        assert snapshot.id is not None
        assert snapshot.parameters["period"] == 25

        # Query back from DB
        db_snap = db.query(StrategyParameterSnapshot).filter_by(id=snapshot.id).first()
        assert db_snap is not None
        assert db_snap.description == "High volatility parameter tuning"
