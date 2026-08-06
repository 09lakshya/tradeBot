"""Unit tests for Benchmark Comparison, Version Tracker, Validation Engine, and Analytics REST APIs."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.domains.analytics.benchmark import BenchmarkComparisonService
from app.domains.analytics.schemas import MonteCarloRequest, WalkForwardRequest
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.analytics.validation import ValidationService
from app.domains.analytics.version_tracker import StrategyVersionTracker
from app.domains.trading.models import Portfolio
from app.main import app


@pytest.fixture
def portfolio(db):
    p = Portfolio(name="Validation Test", initial_capital=Decimal("100000.0000"), cash_balance=Decimal("100000.0000"))
    db.add(p)
    db.flush()
    return p


def test_benchmark_comparison_service(db, portfolio):
    bench_service = BenchmarkComparisonService()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    # Record trades
    for i in range(5):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst_id,
            strategy_id="strat_1", symbol="NIFTY_STK",
            entry_timestamp=now - timedelta(days=5 - i), exit_timestamp=now - timedelta(days=5 - i),
            entry_price=Decimal("100.0000"), exit_price=Decimal("102.0000"),
            quantity=Decimal("10.0000"),
        )

    bench_series = [18000.0, 18100.0, 18050.0, 18200.0, 18300.0]
    result = bench_service.compare_against_benchmark(db, portfolio.id, bench_series, "nifty_50")

    assert result.portfolio_id == portfolio.id
    assert result.benchmark_name == "nifty_50"


def test_strategy_version_tracker(db, portfolio):
    vt_service = StrategyVersionTracker()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst_id,
        strategy_id="ma_cross", strategy_version="1.0.0", symbol="INFY",
        entry_timestamp=now - timedelta(days=2), exit_timestamp=now - timedelta(days=2),
        entry_price=Decimal("1400.0000"), exit_price=Decimal("1450.0000"), quantity=Decimal("10.0000"),
    )
    journal.record_trade(
        db, portfolio_id=portfolio.id, instrument_id=inst_id,
        strategy_id="ma_cross", strategy_version="2.0.0", symbol="INFY",
        entry_timestamp=now - timedelta(days=1), exit_timestamp=now - timedelta(days=1),
        entry_price=Decimal("1450.0000"), exit_price=Decimal("1500.0000"), quantity=Decimal("10.0000"),
    )

    history = vt_service.get_version_history(db, "ma_cross", portfolio.id)
    assert history.strategy_id == "ma_cross"
    assert len(history.versions) == 2
    assert history.versions[0].strategy_version == "1.0.0"
    assert history.versions[1].strategy_version == "2.0.0"


def test_validation_service_monte_carlo_and_walk_forward(db, portfolio):
    val_service = ValidationService()
    journal = TradeJournalService()
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()

    for i in range(10):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst_id,
            strategy_id="strat_val", symbol="NIFTY_STK",
            entry_timestamp=now - timedelta(days=30 - i * 3), exit_timestamp=now - timedelta(days=30 - i * 3 + 1),
            entry_price=Decimal("100.0000"), exit_price=Decimal("105.0000" if i % 2 == 0 else "98.0000"),
            quantity=Decimal("10.0000"),
        )

    # Monte Carlo
    mc_res = val_service.run_monte_carlo(db, portfolio.id, MonteCarloRequest(iterations=100))
    assert mc_res.portfolio_id == portfolio.id
    assert mc_res.iterations == 100
    assert 0.0 <= mc_res.probability_of_ruin <= 1.0

    # Walk Forward
    wf_res = val_service.run_walk_forward(db, portfolio.id, WalkForwardRequest(training_window_days=30, testing_window_days=10))
    assert wf_res.portfolio_id == portfolio.id




def test_analytics_rest_endpoints(db, portfolio):
    from app.core.db import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)

        # Test cost comparison endpoint
        res_cmp = client.post("/api/v1/analytics/cost-comparison?quantity=100&price=1500")
        assert res_cmp.status_code == 200
        data_cmp = res_cmp.json()
        assert "zerodha_2026_v1" in data_cmp["profiles"]

        # Test cost profiles list
        res_prof = client.get("/api/v1/analytics/cost-profiles")
        assert res_prof.status_code == 200

        # Test dashboard endpoint
        res_dash = client.get(f"/api/v1/analytics/dashboard/{portfolio.id}")
        assert res_dash.status_code == 200
        data_dash = res_dash.json()
        assert data_dash["portfolio_id"] == str(portfolio.id)
    finally:
        app.dependency_overrides.pop(get_db, None)

