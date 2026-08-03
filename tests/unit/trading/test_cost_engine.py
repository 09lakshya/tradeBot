"""Unit tests for the CostEngine and Indian statutory fee decompositions."""
from decimal import Decimal
import pytest

from app.domains.market_data.enums import Exchange
from app.domains.trading.cost_engine import (
    CostBreakdown,
    CostEngine,
    TradingCostProfile,
)
from app.domains.trading.enums import OrderSide, ProductType
from app.domains.trading.exceptions import CostProfileNotFoundError


def test_zerodha_delivery_buy_cost():
    engine = CostEngine("zerodha")
    # Buy 100 shares of Reliance at 2500 = 250,000 turnover (Delivery / CNC)
    costs = engine.calculate_cost(
        side=OrderSide.buy,
        product_type=ProductType.cnc,
        exchange=Exchange.NSE,
        quantity=Decimal("100.0000"),
        price=Decimal("2500.0000"),
    )
    assert costs.turnover == Decimal("250000.0000")
    # Brokerage on delivery should be 0 in Zerodha profile
    assert costs.brokerage == Decimal("0.0000")
    # STT delivery buy 0.1% = 250.00
    assert costs.stt == Decimal("250.0000")
    # Exchange charge NSE 0.00297% = 7.425 -> 7.4250
    assert costs.exchange_charges == Decimal("7.4250")
    # SEBI turnover charge 0.0001% (10 per cr) = 0.2500
    assert costs.sebi_charges == Decimal("0.2500")
    # GST 18% on (0 + 7.425 + 0.25) = 18% of 7.675 = 1.3815
    assert costs.gst == Decimal("1.3815")
    # Stamp duty buy delivery 0.015% = 37.5000
    assert costs.stamp_duty == Decimal("37.5000")
    # Total sum
    expected_total = (
        costs.brokerage
        + costs.stt
        + costs.exchange_charges
        + costs.gst
        + costs.stamp_duty
        + costs.sebi_charges
    )
    assert costs.total_charges == expected_total


def test_zerodha_delivery_sell_cost():
    engine = CostEngine("zerodha")
    costs = engine.calculate_cost(
        side=OrderSide.sell,
        product_type=ProductType.cnc,
        exchange=Exchange.NSE,
        quantity=Decimal("100.0000"),
        price=Decimal("2500.0000"),
    )
    assert costs.brokerage == Decimal("0.0000")
    assert costs.stt == Decimal("250.0000")
    # Stamp duty on SELL is 0
    assert costs.stamp_duty == Decimal("0.0000")


def test_intraday_mis_brokerage_cap():
    engine = CostEngine("discount_broker")
    # Turnover 1,000,000 (0.03% = 300, capped at 20)
    costs = engine.calculate_cost(
        side=OrderSide.buy,
        product_type=ProductType.mis,
        exchange=Exchange.NSE,
        quantity=Decimal("1000.0000"),
        price=Decimal("1000.0000"),
    )
    assert costs.brokerage == Decimal("20.0000")


def test_zero_cost_profile():
    engine = CostEngine("zero_cost")
    costs = engine.calculate_cost(
        side=OrderSide.buy,
        product_type=ProductType.cnc,
        exchange=Exchange.NSE,
        quantity=Decimal("100.0000"),
        price=Decimal("2500.0000"),
    )
    assert costs.total_charges == Decimal("0.0000")


def test_custom_profile_registration():
    custom = TradingCostProfile(
        profile_name="institutional_custom",
        brokerage_flat=Decimal("10.0000"),
        brokerage_pct=Decimal("0.0001"),
        brokerage_cap=Decimal("10.0000"),
    )
    CostEngine.register_profile(custom)
    engine = CostEngine()
    costs = engine.calculate_cost(
        side=OrderSide.buy,
        product_type=ProductType.mis,
        exchange=Exchange.NSE,
        quantity=Decimal("100.0000"),
        price=Decimal("1000.0000"),
        profile_name="institutional_custom",
    )
    assert costs.brokerage == Decimal("10.0000")


def test_invalid_profile_raises():
    with pytest.raises(CostProfileNotFoundError):
        CostEngine("non_existent_profile")
