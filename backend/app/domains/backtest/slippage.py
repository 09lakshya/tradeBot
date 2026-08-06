"""Deterministic, Seeded Slippage Models for Backtesting."""
import abc
from decimal import Decimal
import math
import random
import uuid

from app.domains.backtest.schemas import SlippageConfig
from app.domains.trading.enums import OrderSide


def _quantize(val: Decimal | float) -> Decimal:
    if isinstance(val, float):
        val = Decimal(str(round(val, 4)))
    return val.quantize(Decimal("0.0001"))


class BaseSlippageModel(abc.ABC):
    """Abstract interface for slippage calculation."""

    @abc.abstractmethod
    def calculate_fill_price(
        self,
        base_price: Decimal,
        side: OrderSide,
        quantity: Decimal,
        bar_volume: int = 100000,
        bar_high: Decimal | None = None,
        bar_low: Decimal | None = None,
        random_seed: int = 42,
        order_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Calculates (effective_fill_price, slippage_amount).
        slippage_amount is always >= 0.
        Buy fill price = base_price + slippage_amount
        Sell fill price = max(Decimal("0.01"), base_price - slippage_amount)
        """
        pass


class FixedBpsSlippage(BaseSlippageModel):
    """Deterministic fixed basis points slippage."""

    def __init__(self, fixed_bps: Decimal = Decimal("5.0000")):
        self.fixed_bps = fixed_bps

    def calculate_fill_price(
        self,
        base_price: Decimal,
        side: OrderSide,
        quantity: Decimal,
        bar_volume: int = 100000,
        bar_high: Decimal | None = None,
        bar_low: Decimal | None = None,
        random_seed: int = 42,
        order_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        slippage_pct = self.fixed_bps / Decimal("10000.0")
        slippage_amt = _quantize(base_price * slippage_pct)

        if side == OrderSide.buy:
            fill_price = _quantize(base_price + slippage_amt)
        else:
            fill_price = _quantize(max(Decimal("0.0100"), base_price - slippage_amt))

        return fill_price, slippage_amt


class SpreadSlippage(BaseSlippageModel):
    """Spread-based slippage model using high-low range or fixed spread fraction."""

    def __init__(self, spread_pct: Decimal = Decimal("0.5000")):
        self.spread_pct = spread_pct  # Fraction of high-low range (e.g. 0.5 = mid-to-touch)

    def calculate_fill_price(
        self,
        base_price: Decimal,
        side: OrderSide,
        quantity: Decimal,
        bar_volume: int = 100000,
        bar_high: Decimal | None = None,
        bar_low: Decimal | None = None,
        random_seed: int = 42,
        order_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        if bar_high is not None and bar_low is not None and bar_high > bar_low:
            bar_range = bar_high - bar_low
            slippage_amt = _quantize(bar_range * (self.spread_pct / Decimal("10.0")))
        else:
            # Fallback to 5 bps
            slippage_amt = _quantize(base_price * Decimal("0.0005"))

        if side == OrderSide.buy:
            fill_price = _quantize(base_price + slippage_amt)
        else:
            fill_price = _quantize(max(Decimal("0.0100"), base_price - slippage_amt))

        return fill_price, slippage_amt


class VolumeParticipationSlippage(BaseSlippageModel):
    """Square-root market impact model: k * sigma * sqrt(qty / bar_volume)."""

    def __init__(
        self,
        impact_constant_k: Decimal = Decimal("0.1000"),
        fixed_bps_floor: Decimal = Decimal("2.0000"),
    ):
        self.impact_k = impact_constant_k
        self.floor_bps = fixed_bps_floor

    def calculate_fill_price(
        self,
        base_price: Decimal,
        side: OrderSide,
        quantity: Decimal,
        bar_volume: int = 100000,
        bar_high: Decimal | None = None,
        bar_low: Decimal | None = None,
        random_seed: int = 42,
        order_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        effective_vol = max(1, bar_volume)
        participation = float(quantity) / float(effective_vol)
        sqrt_impact = math.sqrt(max(0.0, participation))

        # Intrabar volatility estimate (High - Low) / Open
        if bar_high is not None and bar_low is not None and base_price > Decimal("0.0"):
            sigma = float((bar_high - bar_low) / base_price)
        else:
            sigma = 0.015  # 1.5% default daily volatility

        impact_pct = float(self.impact_k) * sigma * sqrt_impact
        # Enforce floor basis points
        floor_pct = float(self.floor_bps / Decimal("10000.0"))
        total_pct = max(floor_pct, impact_pct)

        slippage_amt = _quantize(float(base_price) * total_pct)

        if side == OrderSide.buy:
            fill_price = _quantize(base_price + slippage_amt)
        else:
            fill_price = _quantize(max(Decimal("0.0100"), base_price - slippage_amt))

        return fill_price, slippage_amt


class SeededPerturbedSlippage(BaseSlippageModel):
    """Decorator adding deterministic pseudo-random jitter around base slippage using explicit seed."""

    def __init__(self, base_model: BaseSlippageModel, jitter_std_bps: Decimal = Decimal("2.0000")):
        self.base_model = base_model
        self.jitter_std_bps = jitter_std_bps

    def calculate_fill_price(
        self,
        base_price: Decimal,
        side: OrderSide,
        quantity: Decimal,
        bar_volume: int = 100000,
        bar_high: Decimal | None = None,
        bar_low: Decimal | None = None,
        random_seed: int = 42,
        order_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal]:
        base_fill, base_slip = self.base_model.calculate_fill_price(
            base_price, side, quantity, bar_volume, bar_high, bar_low, random_seed, order_id
        )

        # Seeded PRNG per order_id + seed for byte-reproducibility
        order_hash = order_id.int if order_id else 0
        rng = random.Random(random_seed ^ (order_hash & 0xFFFFFFFF))
        jitter_factor = Decimal(str(round(rng.gauss(0.0, float(self.jitter_std_bps) / 10000.0), 6)))
        jitter_amt = _quantize(base_price * abs(jitter_factor))

        total_slip = _quantize(base_slip + jitter_amt)
        if side == OrderSide.buy:
            fill_price = _quantize(base_price + total_slip)
        else:
            fill_price = _quantize(max(Decimal("0.0100"), base_price - total_slip))

        return fill_price, total_slip


def create_slippage_model(config: SlippageConfig, random_seed: int = 42) -> BaseSlippageModel:
    """Factory function for slippage models."""
    if config.model_type == "spread_pct":
        return SpreadSlippage(spread_pct=config.spread_pct)
    elif config.model_type == "volume_share" or config.model_type == "square_root_impact":
        return VolumeParticipationSlippage(impact_constant_k=config.impact_constant_k)
    else:
        return FixedBpsSlippage(fixed_bps=config.fixed_bps)
