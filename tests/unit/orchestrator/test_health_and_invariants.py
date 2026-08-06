"""Unit tests for Health Monitoring, Continuous Metrics, and Invariant Verification."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.domains.orchestrator.health import HealthMonitor
from app.domains.orchestrator.invariants import InvariantValidator
from app.domains.orchestrator.metrics import ContinuousMetricsTracker
from app.domains.trading.clock import FixedClock
from app.domains.trading.models import Portfolio, Position


@pytest.fixture
def in_memory_db():
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


def test_health_monitor_latency_recording():
    clock = FixedClock(datetime(2025, 4, 15, 10, 0, 0, tzinfo=timezone.utc))
    monitor = HealthMonitor(clock=clock)

    monitor.record_stage_latency("market_data", 5.2)
    monitor.record_stage_latency("strategies", 12.8)
    monitor.record_stage_latency("portfolio_construction", 3.1)

    report = monitor.get_health_report()
    assert report.overall_status == "healthy"
    assert "market_data" in report.subsystems
    assert report.subsystems["market_data"].latency_ms == 5.2
    assert report.subsystems["market_data"].status == "healthy"


def test_continuous_metrics_tracker():
    tracker = ContinuousMetricsTracker()
    pid = uuid.uuid4()
    now = datetime(2025, 4, 15, 10, 0, 0, tzinfo=timezone.utc)

    portfolio = Portfolio(
        id=pid,
        name="Test Portfolio",
        initial_capital=Decimal("1000000.00"),
        cash_balance=Decimal("950000.00"),
        reserved_cash=Decimal("0.00"),
        base_currency="INR",
        mode="paper",
    )

    pos = Position(
        id=uuid.uuid4(),
        portfolio_id=pid,
        instrument_id=uuid.uuid4(),
        quantity=Decimal("100.00"),
        avg_entry_price=Decimal("500.00"),
    )

    metrics = tracker.calculate_metrics(
        portfolio=portfolio,
        open_positions=[pos],
        current_time=now,
        current_prices={pos.instrument_id: Decimal("550.00")},
    )

    # Total equity = 950,000 cash + 100 * 550 = 1,005,000
    assert metrics.total_equity == Decimal("1005000.00")
    assert metrics.total_pnl == Decimal("5000.00")


def test_invariant_validator_cash_and_positions(in_memory_db):
    validator = InvariantValidator()
    pid = uuid.uuid4()

    p = Portfolio(
        id=pid,
        name="Valid Portfolio",
        initial_capital=Decimal("1000000.00"),
        cash_balance=Decimal("500000.00"),
        reserved_cash=Decimal("50000.00"),
        base_currency="INR",
        mode="paper",
    )
    in_memory_db.add(p)
    in_memory_db.commit()

    report = validator.verify_all(in_memory_db, portfolio_id=pid)
    assert report.all_passed is True
    assert report.cash_reconciled is True
    assert report.positions_consistent is True
