"""Unit tests for Slippage Models."""
from decimal import Decimal
import uuid
import pytest

from app.domains.backtest.schemas import SlippageConfig
from app.domains.backtest.slippage import (
    FixedBpsSlippage,
    SeededPerturbedSlippage,
    SpreadSlippage,
    VolumeParticipationSlippage,
    create_slippage_model,
)
from app.domains.trading.enums import OrderSide


def test_fixed_bps_slippage():
    model = FixedBpsSlippage(fixed_bps=Decimal("5.0000"))

    # Buy order fills higher
    fill_price, slip = model.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.buy,
        quantity=Decimal("10.0000"),
    )
    assert slip == Decimal("0.5000")
    assert fill_price == Decimal("1000.5000")

    # Sell order fills lower
    fill_price_sell, slip_sell = model.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.sell,
        quantity=Decimal("10.0000"),
    )
    assert slip_sell == Decimal("0.5000")
    assert fill_price_sell == Decimal("999.5000")


def test_spread_slippage():
    model = SpreadSlippage(spread_pct=Decimal("0.5000"))
    fill_price, slip = model.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.buy,
        quantity=Decimal("10.0000"),
        bar_high=Decimal("1050.0000"),
        bar_low=Decimal("950.0000"),
    )
    assert slip == Decimal("5.0000")
    assert fill_price == Decimal("1005.0000")


def test_volume_participation_slippage():
    model = VolumeParticipationSlippage(impact_constant_k=Decimal("0.1000"))
    fill_price, slip = model.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.buy,
        quantity=Decimal("10000.0000"),
        bar_volume=100000,
        bar_high=Decimal("1020.0000"),
        bar_low=Decimal("980.0000"),
    )
    assert slip > Decimal("0.0")
    assert fill_price > Decimal("1000.0000")


def test_deterministic_seeded_slippage():
    base = FixedBpsSlippage(fixed_bps=Decimal("5.0000"))
    perturbed = SeededPerturbedSlippage(base, jitter_std_bps=Decimal("2.0000"))
    order_id = uuid.uuid4()

    fill1, slip1 = perturbed.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.buy,
        quantity=Decimal("10.0000"),
        random_seed=12345,
        order_id=order_id,
    )

    fill2, slip2 = perturbed.calculate_fill_price(
        base_price=Decimal("1000.0000"),
        side=OrderSide.buy,
        quantity=Decimal("10.0000"),
        random_seed=12345,
        order_id=order_id,
    )

    assert fill1 == fill2
    assert slip1 == slip2
