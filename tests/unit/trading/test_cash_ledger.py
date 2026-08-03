"""Unit tests for LedgerService and cash balance reconciliation."""
import uuid
from decimal import Decimal
import pytest

from app.domains.trading.enums import TradingMode, TxnType
from app.domains.trading.exceptions import (
    InsufficientBuyingPowerError,
    LedgerReconciliationError,
)
from app.domains.trading.ledger import LedgerService
from app.domains.trading.models import Portfolio


def _create_portfolio(db, init_cash: Decimal = Decimal("50000.0000")) -> Portfolio:
    port = Portfolio(
        name="Test Portfolio",
        mode=TradingMode.paper,
        base_currency="INR",
        initial_capital=init_cash,
        cash_balance=Decimal("0.0000"),
        reserved_cash=Decimal("0.0000"),
    )
    db.add(port)
    db.flush()
    return port


def test_record_transaction_and_reconcile(db):
    ledger = LedgerService(db)
    port = _create_portfolio(db)

    # Initial deposit
    txn1, _ = ledger.record_transaction(
        portfolio_id=port.id,
        txn_type=TxnType.deposit,
        amount=Decimal("50000.0000"),
        description="Initial deposit",
    )
    assert txn1.balance_after == Decimal("50000.0000")
    assert port.cash_balance == Decimal("50000.0000")
    assert ledger.reconcile_balance(port.id) is True

    # Buy fill debit
    txn2, _ = ledger.record_transaction(
        portfolio_id=port.id,
        txn_type=TxnType.buy_fill,
        amount=Decimal("-15000.0000"),
        description="Bought 100 shares",
    )
    assert txn2.balance_after == Decimal("35000.0000")
    assert port.cash_balance == Decimal("35000.0000")
    assert ledger.reconcile_balance(port.id) is True


def test_buying_power_reservation(db):
    ledger = LedgerService(db)
    port = _create_portfolio(db)
    ledger.record_transaction(port.id, TxnType.deposit, Decimal("10000.0000"))

    order_id = uuid.uuid4()
    # Reserve 6000
    ledger.reserve_buying_power(port.id, Decimal("6000.0000"), order_id)
    assert port.reserved_cash == Decimal("6000.0000")
    assert port.cash_balance == Decimal("10000.0000")

    # Attempting to reserve another 5000 should fail (only 4000 available)
    with pytest.raises(InsufficientBuyingPowerError):
        ledger.reserve_buying_power(port.id, Decimal("5000.0000"), order_id)

    # Release 6000
    ledger.release_buying_power(port.id, Decimal("6000.0000"), order_id)
    assert port.reserved_cash == Decimal("0.0000")


def test_reconciliation_tamper_detection(db):
    ledger = LedgerService(db)
    port = _create_portfolio(db)
    ledger.record_transaction(port.id, TxnType.deposit, Decimal("10000.0000"))

    # Tamper cash balance directly without ledger transaction
    port.cash_balance = Decimal("15000.0000")
    db.flush()

    with pytest.raises(LedgerReconciliationError):
        ledger.reconcile_balance(port.id)
