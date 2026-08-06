"""Integration tests verifying OMS order execution through the mandatory pre-trade Risk Gate."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.risk.enums import RiskDecision, ScopeType
from app.domains.risk.models import RiskEvent, RiskLimit
from app.domains.risk.schemas import RiskLimitUpdate
from app.domains.risk.service import RiskService
from app.domains.platform.models import User
from app.domains.trading.clock import FixedClock
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, OrderStatus, OrderType, ProductType, TimeInForce
from app.domains.trading.models import Order, Portfolio
from app.domains.trading.service import TradingService


@pytest.fixture
def db_session():
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
def env(db_session):
    clock = FixedClock(datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc))
    cost_engine = CostEngine()
    risk_service = RiskService(clock=clock)
    trading_service = TradingService(
        db=db_session,
        clock=clock,
        cost_engine=cost_engine,
        risk_service=risk_service,
    )

    user = User(email="risk_integ@tradebot.local", hashed_password="fakehashpassword")
    db_session.add(user)
    db_session.flush()

    portfolio = trading_service.create_portfolio(
        name="Risk OMS Test Portfolio",
        user_id=user.id,
        initial_capital=Decimal("100000.0000"),
    )

    inst_reliance = Instrument(
        trading_symbol="RELIANCE",
        name="Reliance Industries Ltd",
        exchange="NSE",
        asset_class="equity",
        industry="Energy",
        is_active=True,
    )
    inst_tcs = Instrument(
        trading_symbol="TCS",
        name="Tata Consultancy Services Ltd",
        exchange="NSE",
        asset_class="equity",
        industry="IT",
        is_active=True,
    )
    db_session.add_all([inst_reliance, inst_tcs])
    db_session.commit()

    return {
        "db": db_session,
        "clock": clock,
        "trading": trading_service,
        "risk": risk_service,
        "portfolio": portfolio,
        "reliance": inst_reliance,
        "tcs": inst_tcs,
    }


def test_order_passes_risk_gate_and_enters_pending(env):
    """Compliant order passes all risk rules and transitions created -> validated -> accepted -> pending."""
    trading = env["trading"]
    portfolio = env["portfolio"]
    reliance = env["reliance"]

    # ₹5,000 order (5% of 100k equity <= 10% instrument limit)
    order = trading.submit_order(
        portfolio_id=portfolio.id,
        instrument_id=reliance.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("2.0000"),
        limit_price=Decimal("2500.0000"),
    )

    assert order.status == OrderStatus.pending
    assert order.reserved_cash > Decimal("5000.0000")  # Buying power reserved

    # Check risk events recorded in DB
    events = env["db"].execute(
        select(RiskEvent).where(RiskEvent.order_id == order.id)
    ).scalars().all()
    assert len(events) == 10  # All 10 rules passed and recorded
    assert all(e.decision == RiskDecision.passed for e in events)


def test_order_blocked_by_instrument_exposure_limit(env):
    """Order exceeding per-instrument cap is rejected by Risk Gate with zero reserved cash."""
    trading = env["trading"]
    risk = env["risk"]
    portfolio = env["portfolio"]
    reliance = env["reliance"]
    db = env["db"]

    # Configure 10% instrument limit
    risk.update_limits(
        db=db,
        portfolio_id=portfolio.id,
        updates=RiskLimitUpdate(max_instrument_exposure_pct=Decimal("0.1000")),
    )
    db.commit()

    # ₹25,000 order (25% of 100k equity > 10% configured instrument cap)
    order = trading.submit_order(
        portfolio_id=portfolio.id,
        instrument_id=reliance.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("10.0000"),
        limit_price=Decimal("2500.0000"),
    )

    assert order.status == OrderStatus.rejected
    assert "Risk check blocked (exposure_limit)" in order.rejected_reason
    assert order.reserved_cash == Decimal("0.0000")  # No cash reserved for rejected order

    # Verify portfolio buying power remained untouched
    port = env["db"].get(Portfolio, portfolio.id)
    assert port.cash_balance == Decimal("100000.0000")
    assert port.reserved_cash == Decimal("0.0000")


def test_order_blocked_by_active_kill_switch(env):
    """When kill switch is tripped, new orders are immediately rejected by Risk Gate."""
    trading = env["trading"]
    risk = env["risk"]
    portfolio = env["portfolio"]
    reliance = env["reliance"]
    db = env["db"]

    # Trip kill switch
    risk.trip_kill_switch(
        db=db,
        scope=ScopeType.portfolio,
        scope_id=str(portfolio.id),
        reason="Manual trading halt by risk manager",
    )
    db.commit()

    # Submit small compliant order
    order = trading.submit_order(
        portfolio_id=portfolio.id,
        instrument_id=reliance.id,
        side=OrderSide.buy,
        order_type=OrderType.limit,
        quantity=Decimal("1.0000"),
        limit_price=Decimal("2500.0000"),
    )

    assert order.status == OrderStatus.rejected
    assert "Risk check blocked (kill_switch)" in order.rejected_reason
    assert "Manual trading halt" in order.rejected_reason
