"""Indian Market Trading Cost Engine with configurable cost profiles.

Supports full decomposition of statutory fees for NSE and BSE:
- Brokerage (flat per order or percentage with cap)
- STT (Securities Transaction Tax)
- Exchange Transaction Charges
- GST (18% on Brokerage + Exchange + SEBI charges)
- Stamp Duty (Buy side only for delivery)
- SEBI Turnover Charges

All calculations use Decimal arithmetic with zero hardcoded constants.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

from app.domains.market_data.enums import Exchange
from app.domains.trading.enums import OrderSide, ProductType
from app.domains.trading.exceptions import CostProfileNotFoundError

DEC_4DP = Decimal("0.0001")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TradingCostProfile:
    """Configurable cost parameters for a broker / exchange profile."""

    profile_name: str = "default_zerodha"
    brokerage_flat: Decimal = Decimal("20.0000")
    brokerage_pct: Decimal = Decimal("0.0003")  # 0.03%
    brokerage_cap: Decimal = Decimal("20.0000")
    brokerage_delivery_zero: bool = True  # Zerodha delivery is ₹0 brokerage
    stt_delivery_buy_pct: Decimal = Decimal("0.0010")   # 0.1%
    stt_delivery_sell_pct: Decimal = Decimal("0.0010")  # 0.1%
    stt_intraday_buy_pct: Decimal = Decimal("0.0000")   # 0.0%
    stt_intraday_sell_pct: Decimal = Decimal("0.00025") # 0.025%
    exchange_txn_nse_pct: Decimal = Decimal("0.0000297") # 0.00297%
    exchange_txn_bse_pct: Decimal = Decimal("0.0000375") # 0.00375%
    sebi_turnover_pct: Decimal = Decimal("0.0000010")    # ₹10 per crore (0.0001%)
    stamp_duty_delivery_buy_pct: Decimal = Decimal("0.00015")  # 0.015%
    stamp_duty_delivery_sell_pct: Decimal = Decimal("0.0000") # 0%
    stamp_duty_intraday_buy_pct: Decimal = Decimal("0.00003")  # 0.003%
    stamp_duty_intraday_sell_pct: Decimal = Decimal("0.0000")
    gst_pct: Decimal = Decimal("0.1800")  # 18%


@dataclass(frozen=True)
class CostBreakdown:
    """Itemized breakdown of all charges for a trade execution."""

    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    gst: Decimal
    stamp_duty: Decimal
    sebi_charges: Decimal
    total_charges: Decimal


class CostEngine:
    """Calculator for statutory trading fees and brokerages."""

    _PROFILES: ClassVar[dict[str, TradingCostProfile]] = {
        "default": TradingCostProfile(profile_name="default"),
        "zerodha": TradingCostProfile(profile_name="zerodha", brokerage_delivery_zero=True),
        "discount_broker": TradingCostProfile(profile_name="discount_broker", brokerage_delivery_zero=False),
        "zero_cost": TradingCostProfile(
            profile_name="zero_cost",
            brokerage_flat=Decimal("0"),
            brokerage_pct=Decimal("0"),
            brokerage_cap=Decimal("0"),
            brokerage_delivery_zero=True,
            stt_delivery_buy_pct=Decimal("0"),
            stt_delivery_sell_pct=Decimal("0"),
            stt_intraday_buy_pct=Decimal("0"),
            stt_intraday_sell_pct=Decimal("0"),
            exchange_txn_nse_pct=Decimal("0"),
            exchange_txn_bse_pct=Decimal("0"),
            sebi_turnover_pct=Decimal("0"),
            stamp_duty_delivery_buy_pct=Decimal("0"),
            stamp_duty_delivery_sell_pct=Decimal("0"),
            stamp_duty_intraday_buy_pct=Decimal("0"),
            stamp_duty_intraday_sell_pct=Decimal("0"),
            gst_pct=Decimal("0"),
        ),
    }

    def __init__(self, default_profile: str = "default") -> None:
        if default_profile not in self._PROFILES:
            raise CostProfileNotFoundError(default_profile)
        self._default_profile_name = default_profile

    @property
    def default_profile_name(self) -> str:
        return self._default_profile_name

    @classmethod
    def register_profile(cls, profile: TradingCostProfile) -> None:
        cls._PROFILES[profile.profile_name] = profile

    @classmethod
    def get_profile(cls, name: str) -> TradingCostProfile:
        if name not in cls._PROFILES:
            raise CostProfileNotFoundError(name)
        return cls._PROFILES[name]

    def calculate_cost(
        self,
        side: OrderSide,
        product_type: ProductType,
        exchange: Exchange,
        quantity: Decimal,
        price: Decimal,
        profile_name: str | None = None,
    ) -> CostBreakdown:
        """Calculate complete statutory charge breakdown for an order fill."""
        profile = self.get_profile(profile_name or self._default_profile_name)
        turnover = quantity * price

        # 1. Brokerage
        if product_type == ProductType.cnc and profile.brokerage_delivery_zero:
            brokerage = Decimal("0.0000")
        else:
            raw_brokerage = turnover * profile.brokerage_pct
            brokerage = min(raw_brokerage, profile.brokerage_cap)

        # 2. STT
        if product_type == ProductType.cnc:
            stt_rate = profile.stt_delivery_buy_pct if side == OrderSide.buy else profile.stt_delivery_sell_pct
        else:
            stt_rate = profile.stt_intraday_buy_pct if side == OrderSide.buy else profile.stt_intraday_sell_pct
        stt = turnover * stt_rate

        # 3. Exchange Transaction Charges
        exchange_rate = profile.exchange_txn_nse_pct if exchange == Exchange.NSE else profile.exchange_txn_bse_pct
        exchange_charges = turnover * exchange_rate

        # 4. SEBI Turnover Charges
        sebi_charges = turnover * profile.sebi_turnover_pct

        # 5. GST (18% on Brokerage + Exchange Charges + SEBI Charges)
        gst = (brokerage + exchange_charges + sebi_charges) * profile.gst_pct

        # 6. Stamp Duty (Buy side only for delivery)
        if product_type == ProductType.cnc:
            stamp_rate = profile.stamp_duty_delivery_buy_pct if side == OrderSide.buy else profile.stamp_duty_delivery_sell_pct
        else:
            stamp_rate = profile.stamp_duty_intraday_buy_pct if side == OrderSide.buy else profile.stamp_duty_intraday_sell_pct
        stamp_duty = turnover * stamp_rate

        # Total
        total_charges = brokerage + stt + exchange_charges + gst + stamp_duty + sebi_charges

        return CostBreakdown(
            turnover=_quantize(turnover),
            brokerage=_quantize(brokerage),
            stt=_quantize(stt),
            exchange_charges=_quantize(exchange_charges),
            gst=_quantize(gst),
            stamp_duty=_quantize(stamp_duty),
            sebi_charges=_quantize(sebi_charges),
            total_charges=_quantize(total_charges),
        )
