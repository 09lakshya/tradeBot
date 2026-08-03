"""Trading domain enumerations."""
from __future__ import annotations

import enum


class TradingMode(str, enum.Enum):
    paper = "paper"
    live = "live"


class OrderSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, enum.Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


class OrderStatus(str, enum.Enum):
    created = "created"
    validated = "validated"
    accepted = "accepted"
    pending = "pending"
    partial = "partial"
    filled = "filled"
    cancelled = "cancelled"
    rejected = "rejected"
    expired = "expired"


class PositionStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class ProductType(str, enum.Enum):
    cnc = "cnc"  # Cash & Carry / Delivery
    mis = "mis"  # Margin Intraday Square-off


class TimeInForce(str, enum.Enum):
    day = "day"
    gtc = "gtc"
    ioc = "ioc"


class TxnType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    buy_fill = "buy_fill"
    sell_fill = "sell_fill"
    brokerage = "brokerage"
    stt = "stt"
    exchange_fee = "exchange_fee"
    gst = "gst"
    stamp_duty = "stamp_duty"
    sebi_turnover_fee = "sebi_turnover_fee"
    dividend = "dividend"
