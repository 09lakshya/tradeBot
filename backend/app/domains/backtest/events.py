"""Deterministic event structures for the Backtesting priority event loop."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domains.trading.enums import OrderSide, OrderType, ProductType


@dataclass(order=True)
class PriorityEvent:
    """Base event class with priority-based deterministic ordering.
    Python heapq / PriorityQueue sorts by fields in order: timestamp, priority, sequence_id.
    """
    timestamp: datetime
    priority: int
    sequence_id: int = field(compare=True)
    event_id: uuid.UUID = field(default_factory=uuid.uuid4, compare=False)


@dataclass(order=True)
class MarketBarEvent(PriorityEvent):
    """Historical bar delivery event to the backtest engine and strategy."""
    instrument_id: uuid.UUID = field(compare=False, default=None)
    symbol: str = field(compare=False, default="")
    open: Decimal = field(compare=False, default=Decimal("0.0000"))
    high: Decimal = field(compare=False, default=Decimal("0.0000"))
    low: Decimal = field(compare=False, default=Decimal("0.0000"))
    close: Decimal = field(compare=False, default=Decimal("0.0000"))
    volume: int = field(compare=False, default=0)
    timeframe: str = field(compare=False, default="1d")


@dataclass(order=True)
class CorporateActionEvent(PriorityEvent):
    """Corporate action processing event (splits, dividends, bonus)."""
    instrument_id: uuid.UUID = field(compare=False, default=None)
    action_type: str = field(compare=False, default="")
    ratio: Decimal = field(compare=False, default=Decimal("1.0000"))
    dividend_amount: Decimal = field(compare=False, default=Decimal("0.0000"))


@dataclass(order=True)
class SignalEvent(PriorityEvent):
    """Strategy generated trading signal."""
    strategy_id: str = field(compare=False, default="")
    instrument_id: uuid.UUID = field(compare=False, default=None)
    symbol: str = field(compare=False, default="")
    side: OrderSide = field(compare=False, default=OrderSide.buy)
    target_quantity: Decimal = field(compare=False, default=Decimal("0.0000"))
    order_type: OrderType = field(compare=False, default=OrderType.market)
    limit_price: Decimal | None = field(compare=False, default=None)
    stop_loss: Decimal | None = field(compare=False, default=None)
    take_profit: Decimal | None = field(compare=False, default=None)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)


@dataclass(order=True)
class OrderSubmissionEvent(PriorityEvent):
    """Order placement event through TradingService and Risk Gate."""
    portfolio_id: uuid.UUID = field(compare=False, default=None)
    instrument_id: uuid.UUID = field(compare=False, default=None)
    side: OrderSide = field(compare=False, default=OrderSide.buy)
    order_type: OrderType = field(compare=False, default=OrderType.market)
    quantity: Decimal = field(compare=False, default=Decimal("0.0000"))
    limit_price: Decimal | None = field(compare=False, default=None)
    product_type: ProductType = field(compare=False, default=ProductType.cnc)
    signal_id: uuid.UUID | None = field(compare=False, default=None)


@dataclass(order=True)
class FillExecutionEvent(PriorityEvent):
    """Execution simulator fill event at bar t+1 open with slippage."""
    order_id: uuid.UUID = field(compare=False, default=None)
    instrument_id: uuid.UUID = field(compare=False, default=None)
    bar_open_price: Decimal = field(compare=False, default=Decimal("0.0000"))
    bar_high_price: Decimal = field(compare=False, default=Decimal("0.0000"))
    bar_low_price: Decimal = field(compare=False, default=Decimal("0.0000"))
    bar_volume: int = field(compare=False, default=0)


@dataclass(order=True)
class TimerEvent(PriorityEvent):
    """Timer event for intraday / EOD Mark-to-Market valuation and session bounds."""
    timer_type: str = field(compare=False, default="eod_valuation")
