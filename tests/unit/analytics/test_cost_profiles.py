"""Unit tests for Trading Cost Profile Engine."""
from decimal import Decimal
import pytest

from app.domains.analytics.cost_profiles import CostProfileManager
from app.domains.analytics.schemas import CostProfileCreateRequest
from app.domains.market_data.enums import Exchange
from app.domains.trading.enums import OrderSide, ProductType


def test_builtin_cost_profiles():
    mgr = CostProfileManager()
    builtins = mgr.get_builtin_profiles()
    assert "ideal" in builtins
    assert "indian_equity_delivery" in builtins
    assert "zerodha_2026_v1" in builtins
    assert "groww_2026_v1" in builtins
    assert "icici_2026_v1" in builtins


def test_calculate_trade_costs():
    mgr = CostProfileManager()
    costs = mgr.calculate_trade_costs(
        side=OrderSide.buy,
        product_type=ProductType.cnc,
        exchange=Exchange.NSE,
        quantity=Decimal("100.0000"),
        price=Decimal("1000.0000"),
        profile_name="zerodha_2026_v1",
    )

    # Zerodha delivery brokerage is ₹0
    assert costs.brokerage == Decimal("0.0000")
    # STT: 0.1% of 100,000 = ₹100
    assert costs.stt == Decimal("100.0000")
    assert costs.total_charges > Decimal("100.0000")


def test_custom_cost_profile_creation(db):
    mgr = CostProfileManager()
    req = CostProfileCreateRequest(
        profile_name="custom_discount",
        version="1.0.0",
        brokerage_flat=Decimal("15.0000"),
        brokerage_pct=Decimal("0.0002"),
    )
    rec = mgr.create_profile(db, req)
    assert rec.profile_name == "custom_discount"

    fetched = mgr.get_profile(db, "custom_discount")
    assert fetched is not None
    assert fetched.version == "1.0.0"


def test_cost_comparison():
    mgr = CostProfileManager()
    cmp = mgr.get_cost_comparison(
        quantity=Decimal("100.0000"),
        price=Decimal("1500.0000"),
        profile_names=["zerodha_2026_v1", "groww_2026_v1", "icici_2026_v1"],
    )

    assert cmp.turnover == Decimal("150000.0000")
    assert "zerodha_2026_v1" in cmp.profiles
    assert "groww_2026_v1" in cmp.profiles
    assert "icici_2026_v1" in cmp.profiles
