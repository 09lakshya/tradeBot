"""Paper execution simulator modeling realistic market dynamics.

Simulates:
- Market orders with configurable slippage (in basis points or spread percentage)
- Limit orders against market price / bar ticks
- Stop and Stop-Limit triggers
- Partial fills
- Latency time offset simulation
- Exact Indian statutory fees via CostEngine
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.domains.market_data.enums import Exchange
from app.domains.trading.clock import Clock
from app.domains.trading.cost_engine import CostBreakdown, CostEngine
from app.domains.trading.enums import OrderSide, OrderType
from app.domains.trading.models import Order

DEC_4DP = Decimal("0.0001")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FillResult:
    """Execution output from simulator."""

    quantity: Decimal
    price: Decimal
    slippage: Decimal
    costs: CostBreakdown
    filled_at: datetime


class ExecutionSimulator:
    """Simulates realistic order execution in a paper trading environment."""

    def __init__(
        self,
        cost_engine: CostEngine,
        clock: Clock,
        slippage_bps: Decimal = Decimal("5.0"),  # 5 bps = 0.05%
        latency_ms: int = 50,
        cost_profile: str = "default",
    ) -> None:
        self._cost_engine = cost_engine
        self._clock = clock
        self.slippage_bps = slippage_bps
        self.latency_ms = latency_ms
        self.cost_profile = cost_profile

    def _apply_slippage(self, side: OrderSide, base_price: Decimal) -> tuple[Decimal, Decimal]:
        """Apply basis points slippage: adverse impact on market orders."""
        slippage_rate = (self.slippage_bps / Decimal("10000.0"))
        if side == OrderSide.buy:
            exec_price = base_price * (Decimal("1.0") + slippage_rate)
        else:
            exec_price = base_price * (Decimal("1.0") - slippage_rate)
        slippage_amount = abs(exec_price - base_price)
        return _quantize(exec_price), _quantize(slippage_amount)

    def evaluate_execution(
        self,
        order: Order,
        market_price: Decimal,
        exchange: Exchange = Exchange.NSE,
        fill_quantity: Decimal | None = None,
    ) -> FillResult | None:
        """Evaluate if and at what price an order fills given current market conditions."""
        remaining_qty = order.quantity - order.filled_quantity
        if remaining_qty <= Decimal("0.0000"):
            return None

        qty_to_fill = _quantize(fill_quantity or remaining_qty)
        qty_to_fill = min(qty_to_fill, remaining_qty)

        # 1. Market Orders
        if order.order_type == OrderType.market:
            exec_price, slippage = self._apply_slippage(order.side, market_price)

        # 2. Limit Orders
        elif order.order_type == OrderType.limit:
            if order.limit_price is None:
                return None
            if order.side == OrderSide.buy:
                # Buy limit fills if market price is at or below limit
                if market_price > order.limit_price:
                    return None
                exec_price = min(market_price, order.limit_price)
                slippage = Decimal("0.0000")
            else:
                # Sell limit fills if market price is at or above limit
                if market_price < order.limit_price:
                    return None
                exec_price = max(market_price, order.limit_price)
                slippage = Decimal("0.0000")

        # 3. Stop Orders
        elif order.order_type == OrderType.stop:
            if order.stop_price is None:
                return None
            if order.side == OrderSide.buy:
                if market_price < order.stop_price:
                    return None
            else:
                if market_price > order.stop_price:
                    return None
            exec_price, slippage = self._apply_slippage(order.side, market_price)

        # 4. Stop Limit Orders
        elif order.order_type == OrderType.stop_limit:
            if order.stop_price is None or order.limit_price is None:
                return None
            if order.side == OrderSide.buy:
                if market_price < order.stop_price or market_price > order.limit_price:
                    return None
                exec_price = min(market_price, order.limit_price)
            else:
                if market_price > order.stop_price or market_price < order.limit_price:
                    return None
                exec_price = max(market_price, order.limit_price)
            slippage = Decimal("0.0000")

        else:
            return None

        # Calculate Indian market statutory charges
        costs = self._cost_engine.calculate_cost(
            side=order.side,
            product_type=order.product_type,
            exchange=exchange,
            quantity=qty_to_fill,
            price=exec_price,
            profile_name=self.cost_profile,
        )

        fill_time = self._clock.now() + timedelta(milliseconds=self.latency_ms)

        return FillResult(
            quantity=qty_to_fill,
            price=exec_price,
            slippage=slippage,
            costs=costs,
            filled_at=fill_time,
        )
