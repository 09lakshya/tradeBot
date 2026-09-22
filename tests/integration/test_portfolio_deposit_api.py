"""Integration tests for topping up a portfolio's cash.

Capital used to enter only at portfolio creation, so a funded account could
never be added to. These cover the deposit endpoint end to end: the balance
moves, the immutable ledger records it, and bad input is refused.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.domains.trading.enums import TxnType
from app.domains.trading.models import Portfolio, Transaction
from app.main import app


@pytest.fixture
def client_and_session() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)

    def override_get_db() -> Iterator[Session]:
        session = maker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, maker
    app.dependency_overrides.clear()
    engine.dispose()


def _create_portfolio(client: TestClient, initial: str = "0") -> str:
    res = client.post(
        "/api/v1/trading/portfolios",
        json={"name": "Wallet", "initial_capital": initial},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_deposit_credits_cash_and_records_a_ledger_entry(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, maker = client_and_session
    portfolio_id = _create_portfolio(client, initial="0")

    res = client.post(
        f"/api/v1/trading/portfolios/{portfolio_id}/deposit",
        json={"amount": "50000.00", "description": "Initial funding"},
    )
    assert res.status_code == 200, res.text
    assert Decimal(res.json()["cash_balance"]) == Decimal("50000.0000")

    with maker() as session:
        txns = session.scalars(
            select(Transaction).where(Transaction.portfolio_id == uuid.UUID(portfolio_id))
        ).all()
        deposits = [t for t in txns if t.txn_type == TxnType.deposit]
        assert len(deposits) == 1
        assert deposits[0].amount == Decimal("50000.0000")
        assert deposits[0].balance_after == Decimal("50000.0000")
        assert deposits[0].reference_type == "cash_deposit"


def test_deposits_accumulate(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """The gap this closes: a second credit onto an already-funded wallet."""
    client, maker = client_and_session
    portfolio_id = _create_portfolio(client, initial="1000")

    for amount in ("2500.50", "499.50"):
        res = client.post(
            f"/api/v1/trading/portfolios/{portfolio_id}/deposit", json={"amount": amount}
        )
        assert res.status_code == 200, res.text

    assert Decimal(res.json()["cash_balance"]) == Decimal("4000.0000")

    with maker() as session:
        portfolio = session.get(Portfolio, uuid.UUID(portfolio_id))
        assert portfolio is not None
        assert portfolio.cash_balance == Decimal("4000.0000")
        # Initial capital is not rewritten by a top-up; only cash moves.
        assert portfolio.initial_capital == Decimal("1000.0000")


def test_deposit_to_unknown_portfolio_is_404(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    res = client.post(
        f"/api/v1/trading/portfolios/{uuid.uuid4()}/deposit", json={"amount": "100"}
    )
    assert res.status_code == 404


@pytest.mark.parametrize("amount", ["0", "-250.00"])
def test_non_positive_deposits_are_refused(
    client_and_session: tuple[TestClient, sessionmaker[Session]], amount: str
) -> None:
    client, maker = client_and_session
    portfolio_id = _create_portfolio(client, initial="500")

    res = client.post(
        f"/api/v1/trading/portfolios/{portfolio_id}/deposit", json={"amount": amount}
    )
    assert res.status_code == 422

    with maker() as session:
        portfolio = session.get(Portfolio, uuid.UUID(portfolio_id))
        assert portfolio is not None
        assert portfolio.cash_balance == Decimal("500.0000")
