"""FastAPI REST API router for Trading domain."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.trading.deps import get_trading_service
from app.domains.trading.enums import OrderStatus, PositionStatus
from app.domains.trading.exceptions import (
    DuplicateIdempotencyKeyError,
    InsufficientBuyingPowerError,
    InsufficientPositionQuantityError,
    InvalidOrderPriceError,
    InvalidOrderQuantityError,
    InvalidStateTransitionError,
    OrderNotCancellableError,
    OrderNotFoundError,
    PortfolioNotFoundError,
    PositionNotFoundError,
)
from app.domains.trading.models import Order, Portfolio, Position, Transaction
from app.domains.trading.schemas import (
    FillResponse,
    OrderCancelRequest,
    OrderExecuteRequest,
    OrderResponse,
    OrderSubmitRequest,
    PortfolioCreateRequest,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionResponse,
    TransactionResponse,
)
from app.domains.trading.service import TradingService

router = APIRouter()


@router.post("/portfolios", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    request: PortfolioCreateRequest,
    service: Annotated[TradingService, Depends(get_trading_service)],
) -> Portfolio:
    """Create a new paper trading portfolio with initial capital."""
    return service.create_portfolio(
        name=request.name,
        initial_capital=request.initial_capital,
        mode=request.mode,
        user_id=request.user_id,
        base_currency=request.base_currency,
    )


@router.get("/portfolios", response_model=list[PortfolioResponse])
def list_portfolios(
    db: Annotated[Session, Depends(get_db)],
    user_id: uuid.UUID | None = Query(None),
) -> list[Portfolio]:
    """List all portfolio accounts."""
    stmt = select(Portfolio)
    if user_id:
        stmt = stmt.where(Portfolio.user_id == user_id)
    return list(db.execute(stmt).scalars().all())


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Portfolio:
    """Fetch specific portfolio by ID."""
    portfolio = db.execute(select(Portfolio).where(Portfolio.id == portfolio_id)).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    return portfolio


@router.get("/portfolios/{portfolio_id}/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    portfolio_id: uuid.UUID,
    service: Annotated[TradingService, Depends(get_trading_service)],
) -> PortfolioSummaryResponse:
    """Get consolidated financial valuation and net liquidation value for portfolio."""
    try:
        summary = service.get_portfolio_summary(portfolio_id)
        return PortfolioSummaryResponse(**summary.__dict__)
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def submit_order(
    request: OrderSubmitRequest,
    service: Annotated[TradingService, Depends(get_trading_service)],
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> Order:
    """Submit trade order to OMS with state machine validation and buying power checks."""
    idemp_key = request.idempotency_key or x_idempotency_key
    try:
        return service.submit_order(
            portfolio_id=request.portfolio_id,
            instrument_id=request.instrument_id,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            product_type=request.product_type,
            time_in_force=request.time_in_force,
            idempotency_key=idemp_key,
            decision=request.decision.model_dump() if request.decision else None,
        )
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InsufficientBuyingPowerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (InvalidOrderQuantityError, InvalidOrderPriceError, InvalidStateTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (PortfolioNotFoundError, PositionNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    portfolio_id: uuid.UUID | None = Query(None),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    limit: int = Query(100, le=500),
) -> list[Order]:
    """List orders with optional portfolio and status filters."""
    stmt = select(Order)
    if portfolio_id:
        stmt = stmt.where(Order.portfolio_id == portfolio_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    stmt = stmt.order_by(Order.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Order:
    """Fetch order details and execution fills."""
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: uuid.UUID,
    request: OrderCancelRequest,
    service: Annotated[TradingService, Depends(get_trading_service)],
) -> Order:
    """Cancel an active order."""
    try:
        return service.cancel_order(order_id=order_id, reason=request.reason)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderNotCancellableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/orders/{order_id}/execute", response_model=FillResponse | None)
def execute_order(
    order_id: uuid.UUID,
    request: OrderExecuteRequest,
    service: Annotated[TradingService, Depends(get_trading_service)],
) -> FillResponse | None:
    """Simulate execution fill against market price."""
    try:
        fill = service.execute_order(
            order_id=order_id,
            market_price=request.market_price,
            exchange=request.exchange,
            fill_quantity=request.fill_quantity,
        )
        if fill is None:
            return None
        return FillResponse.model_validate(fill)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientPositionQuantityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions", response_model=list[PositionResponse])
def list_positions(
    db: Annotated[Session, Depends(get_db)],
    portfolio_id: uuid.UUID = Query(...),
    status_filter: PositionStatus | None = Query(None, alias="status"),
) -> list[Position]:
    """List positions and FIFO lots for a portfolio."""
    stmt = select(Position).where(Position.portfolio_id == portfolio_id)
    if status_filter:
        stmt = stmt.where(Position.status == status_filter)
    return list(db.execute(stmt).scalars().all())


@router.get("/ledger", response_model=list[TransactionResponse])
def list_ledger_transactions(
    db: Annotated[Session, Depends(get_db)],
    portfolio_id: uuid.UUID = Query(...),
    limit: int = Query(100, le=1000),
) -> list[Transaction]:
    """Retrieve immutable double-entry ledger history."""
    stmt = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.post("/portfolios/{portfolio_id}/reconcile")
def reconcile_portfolio(
    portfolio_id: uuid.UUID,
    service: Annotated[TradingService, Depends(get_trading_service)],
) -> dict[str, str | bool]:
    """Assert cash balance reconciliation with transaction ledger."""
    try:
        ok = service.ledger.reconcile_balance(portfolio_id)
        return {"reconciled": ok, "status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
