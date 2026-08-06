"""Unit tests for KillSwitch and CircuitBreaker state management."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.domains.risk.circuit_breaker import CircuitBreakerManager, KillSwitchManager
from app.domains.risk.enums import BreakerState, ScopeType
from app.domains.trading.clock import FixedClock


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


def test_kill_switch_trip_and_audited_reset(mem_db):
    start_time = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(start_time)
    ks_mgr = KillSwitchManager(mem_db, clock)
    port_id = str(uuid.uuid4())

    # Initial state: not tripped
    assert not ks_mgr.is_tripped(ScopeType.portfolio, port_id)

    # Trip kill switch
    ks = ks_mgr.trip(
        scope=ScopeType.portfolio,
        scope_id=port_id,
        reason="Manual emergency halt triggered by risk desk",
        activated_by="risk_officer_1",
    )
    assert ks.is_active is True
    assert ks.reason == "Manual emergency halt triggered by risk desk"
    assert ks.activated_by == "risk_officer_1"
    assert ks.activated_at == start_time
    assert ks_mgr.is_tripped(ScopeType.portfolio, port_id)

    # Advance clock and reset with audit reason
    clock.advance(timedelta(minutes=30))
    reset_time = clock.now()

    reset_ks = ks_mgr.reset(
        scope=ScopeType.portfolio,
        scope_id=port_id,
        reset_reason="Issue investigated and resolved",
        reset_by="head_of_trading",
    )
    assert reset_ks.is_active is False
    assert reset_ks.reset_reason == "Issue investigated and resolved"
    assert reset_ks.reset_by == "head_of_trading"
    assert reset_ks.reset_at == reset_time
    assert not ks_mgr.is_tripped(ScopeType.portfolio, port_id)


def test_circuit_breaker_cooldown_and_half_open(mem_db):
    start_time = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(start_time)
    cb_mgr = CircuitBreakerManager(mem_db, clock)
    port_id = str(uuid.uuid4())

    # Trip breaker for 300 seconds (5 mins)
    cb = cb_mgr.trip(
        scope=ScopeType.portfolio,
        scope_id=port_id,
        reason="Rapid loss limit soft breach",
        cooloff_seconds=300,
    )
    assert cb.state == BreakerState.tripped
    assert cb.trip_count == 1
    assert cb.cooloff_until == start_time + timedelta(seconds=300)

    # Advance 2 minutes (still in cooldown)
    clock.advance(timedelta(minutes=2))
    cb_checked = cb_mgr.check_and_update(ScopeType.portfolio, port_id)
    assert cb_checked.state == BreakerState.tripped

    # Advance beyond 5 minutes (transitions to half_open)
    clock.advance(timedelta(minutes=4))  # Total 6 mins
    cb_half = cb_mgr.check_and_update(ScopeType.portfolio, port_id)
    assert cb_half.state == BreakerState.half_open

    # Reset breaker back to armed
    cb_armed = cb_mgr.reset(ScopeType.portfolio, port_id)
    assert cb_armed.state == BreakerState.armed
    assert cb_armed.cooloff_until is None
