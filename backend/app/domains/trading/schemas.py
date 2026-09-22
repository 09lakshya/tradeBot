"""Pydantic schemas and DTOs for the Trading domain REST API."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.market_data.enums import Exchange
from app.domains.trading.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    ProductType,
    TimeInForce,
    TradingMode,
    TxnType,
)


class PortfolioCreateRequest(BaseModel):
    name: str = Field(..., max_length=100, examples=["Main Paper Strategy"])
    initial_capital: Decimal = Field(Decimal("1000000.0000"), ge=0, examples=[1000000.00])
    mode: TradingMode = TradingMode.paper
    base_currency: str = Field("INR", max_length=10)
    user_id: uuid.UUID | None = None


class PortfolioDepositRequest(BaseModel):
    """Top up an existing portfolio's cash. `gt=0` keeps a deposit a credit:
    withdrawals are a separate concern with their own balance checks."""

    amount: Decimal = Field(..., gt=0, examples=[50000.00])
    description: str | None = Field(None, max_length=255)


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    name: str
    mode: TradingMode
    base_currency: str
    initial_capital: Decimal
    cash_balance: Decimal
    reserved_cash: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


class PortfolioSummaryResponse(BaseModel):
    portfolio_id: uuid.UUID
    name: str
    mode: str
    base_currency: str
    initial_capital: Decimal
    cash_balance: Decimal
    reserved_cash: Decimal
    available_buying_power: Decimal
    invested_capital: Decimal
    open_positions_market_value: Decimal
    portfolio_total_value: Decimal
    total_realized_pnl: Decimal
    total_unrealized_pnl: Decimal
    open_positions_count: int


class OrderDecisionCreate(BaseModel):
    model_confidence: Decimal | None = Field(None, ge=0, le=1)
    expected_return: Decimal | None = None
    risk_reward_ratio: Decimal | None = None
    market_regime: str | None = None
    entry_reason: str = Field(..., max_length=500)
    exit_reason: str | None = Field(None, max_length=500)
    summary: str = Field(..., max_length=1000)
    raw_signals: dict | None = None


class OrderDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    model_confidence: Decimal | None
    expected_return: Decimal | None
    risk_reward_ratio: Decimal | None
    market_regime: str | None
    entry_reason: str
    exit_reason: str | None
    summary: str
    raw_signals: dict | None


class OrderSubmitRequest(BaseModel):
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0)
    limit_price: Decimal | None = Field(None, gt=0)
    stop_price: Decimal | None = Field(None, gt=0)
    product_type: ProductType = ProductType.cnc
    time_in_force: TimeInForce = TimeInForce.day
    idempotency_key: str | None = Field(None, max_length=64)
    decision: OrderDecisionCreate | None = None


class FillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    fill_sequence: int
    quantity: Decimal
    price: Decimal
    slippage: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    gst: Decimal
    stamp_duty: Decimal
    sebi_charges: Decimal
    total_charges: Decimal
    filled_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    side: OrderSide
    order_type: OrderType
    product_type: ProductType
    time_in_force: TimeInForce
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    avg_fill_price: Decimal | None
    status: OrderStatus
    idempotency_key: str | None
    rejected_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    decision: OrderDecisionResponse | None = None
    fills: list[FillResponse] = []


class OrderCancelRequest(BaseModel):
    reason: str = Field("User requested cancellation", max_length=255)


class OrderExecuteRequest(BaseModel):
    market_price: Decimal = Field(..., gt=0)
    exchange: Exchange = Exchange.NSE
    fill_quantity: Decimal | None = Field(None, gt=0)


class PositionLotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position_id: uuid.UUID
    fill_id: uuid.UUID
    initial_quantity: Decimal
    remaining_quantity: Decimal
    price: Decimal
    opened_at: datetime


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    product_type: ProductType
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    status: PositionStatus
    version: int
    created_at: datetime
    updated_at: datetime
    lots: list[PositionLotResponse] = []


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    txn_type: TxnType
    amount: Decimal
    balance_after: Decimal
    related_order_id: uuid.UUID | None
    related_fill_id: uuid.UUID | None
    reference_type: str | None
    description: str | None
    created_at: datetime

