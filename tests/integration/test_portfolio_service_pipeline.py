"""Integration tests for PortfolioConstructionService with database persistence."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.portfolio.models import (
    ArbitrationAuditRecord,
    CandidateOrderRecord,
    PortfolioConstructionPlan,
)
from app.domains.portfolio.schemas import PortfolioConstructionConfig
from app.domains.portfolio.service import PortfolioConstructionService
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.clock import FixedClock
from app.domains.trading.models import Portfolio, Position


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_portfolio_service_persists_plan_and_candidates(db_session: Session):
    clock = FixedClock(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc))
    service = PortfolioConstructionService(clock=clock)

    portfolio_id = uuid.uuid4()
    portfolio = Portfolio(
        id=portfolio_id,
        name="Main Fund",
        base_currency="INR",
        initial_capital=Decimal("500000.00"),
        cash_balance=Decimal("500000.00"),
        reserved_cash=Decimal("0.00"),
    )
    db_session.add(portfolio)

    inst_id = uuid.uuid4()
    inst = Instrument(
        id=inst_id,
        trading_symbol="TCS",
        name="Tata Consultancy Services",
        exchange=Exchange.NSE,
        lot_size=1,
    )
    db_session.add(inst)
    db_session.commit()

    sig = TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id="trend_following",
        instrument_id=inst_id,
        symbol="TCS",
        timestamp=clock.now(),
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=0.88,
        entry_price=Decimal("3500.00"),
        stop_loss=Decimal("3400.00"),
        take_profit=Decimal("3700.00"),
    )

    snapshot = service.build_snapshot_from_db(
        db=db_session,
        portfolio_id=portfolio_id,
        current_prices={inst_id: Decimal("3500.00")},
    )

    plan_resp = service.construct_portfolio(
        portfolio_snapshot=snapshot,
        signals=[sig],
        current_prices={inst_id: Decimal("3500.00")},
        db=db_session,
    )
    db_session.commit()

    assert plan_resp.total_candidates == 1

    # Verify DB records
    saved_plan = db_session.get(PortfolioConstructionPlan, plan_resp.plan_id)
    assert saved_plan is not None
    assert len(saved_plan.candidate_orders) == 1
    assert len(saved_plan.arbitration_records) == 1

    cand_rec = saved_plan.candidate_orders[0]
    assert cand_rec.symbol == "TCS"
    assert cand_rec.side == "buy"
    assert cand_rec.quantity > 0
