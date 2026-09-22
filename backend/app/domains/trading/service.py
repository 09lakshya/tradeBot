"""Trading and Order Management System (OMS) orchestrator service."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.market_data.enums import Exchange
from app.domains.market_data.models import Instrument
from app.domains.risk.enums import RiskDecision
from app.domains.risk.service import RiskService
from app.domains.trading.audit import AuditLogService
from app.domains.trading.clock import Clock
from app.domains.trading.cost_engine import CostEngine
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
from app.domains.trading.events import (
    OrderAcceptedEvent,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderFilledEvent,
    OrderPartiallyFilledEvent,
    OrderPendingEvent,
    OrderRejectedEvent,
    OrderValidatedEvent,
)
from app.domains.trading.exceptions import (
    DuplicateIdempotencyKeyError,
    InstrumentNotFoundError,
    InvalidOrderPriceError,
    InvalidOrderQuantityError,
    OrderNotCancellableError,
    OrderNotFoundError,
    PortfolioNotFoundError,
)
from app.domains.trading.ledger import LedgerService
from app.domains.trading.models import (
    Fill,
    Order,
    OrderDecision,
    Portfolio,
    Position,
)
from app.domains.trading.positions import PositionManager
from app.domains.trading.simulator import ExecutionSimulator
from app.domains.trading.state_machine import OrderStateMachine

DEC_4DP = Decimal("0.0001")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(DEC_4DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PortfolioSummary:
    """Consolidated financial summary of a portfolio."""

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


class TradingService:
    """Coordinates portfolios, orders, execution simulation, positions, and ledger."""

    def __init__(
        self,
        db: Session,
        clock: Clock,
        cost_engine: CostEngine | None = None,
        simulator: ExecutionSimulator | None = None,
        risk_service: RiskService | None = None,
    ) -> None:
        self._db = db
        self._clock = clock
        self._cost_engine = cost_engine or CostEngine()
        self._simulator = simulator or ExecutionSimulator(
            cost_engine=self._cost_engine,
            clock=self._clock,
            cost_profile=self._cost_engine.default_profile_name,
        )
        self._risk_service = risk_service or RiskService(clock=self._clock)
        self._ledger = LedgerService(db)
        self._positions = PositionManager(db, clock)
        self._audit = AuditLogService(db)

    @property
    def ledger(self) -> LedgerService:
        return self._ledger

    @property
    def positions(self) -> PositionManager:
        return self._positions

    @property
    def audit(self) -> AuditLogService:
        return self._audit

    def create_portfolio(
        self,
        name: str,
        initial_capital: Decimal,
        mode: TradingMode = TradingMode.paper,
        user_id: uuid.UUID | None = None,
        base_currency: str = "INR",
        correlation_id: uuid.UUID | None = None,
    ) -> Portfolio:
        """Create a new portfolio account and credit initial capital to the ledger."""
        corr_id = correlation_id or uuid.uuid4()
        init_cap = _quantize(initial_capital)

        portfolio = Portfolio(
            user_id=user_id,
            name=name,
            mode=mode,
            base_currency=base_currency,
            initial_capital=init_cap,
            cash_balance=Decimal("0.0000"),
            reserved_cash=Decimal("0.0000"),
        )
        self._db.add(portfolio)
        self._db.flush()

        # Credit initial capital via immutable ledger
        if init_cap > Decimal("0.0000"):
            _, evt = self._ledger.record_transaction(
                portfolio_id=portfolio.id,
                txn_type=TxnType.deposit,
                amount=init_cap,
                reference_type="initial_deposit",
                description="Initial portfolio capital deposit",
                correlation_id=corr_id,
            )
            self._audit.record_event(evt)

        return portfolio

    def deposit_cash(
        self,
        portfolio_id: uuid.UUID,
        amount: Decimal,
        description: str | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> Portfolio:
        """Credit cash to an existing portfolio through the immutable ledger.

        Capital could previously only enter at portfolio creation, so a funded
        account could never be topped up. Routed through ``record_transaction``
        so the deposit is an auditable ledger entry with its own event, exactly
        like the initial capital credit.
        """
        corr_id = correlation_id or uuid.uuid4()
        credit = _quantize(amount)
        if credit <= Decimal("0.0000"):
            raise ValueError("Deposit amount must be greater than zero")

        _, evt = self._ledger.record_transaction(
            portfolio_id=portfolio_id,
            txn_type=TxnType.deposit,
            amount=credit,
            reference_type="cash_deposit",
            description=description or "Cash deposit",
            correlation_id=corr_id,
        )
        self._audit.record_event(evt)

        portfolio = self._db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if portfolio is None:  # pragma: no cover - the ledger raises first
            raise PortfolioNotFoundError(portfolio_id)
        return portfolio

    def submit_order(
        self,
        portfolio_id: uuid.UUID,
        instrument_id: uuid.UUID,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        product_type: ProductType = ProductType.cnc,
        time_in_force: TimeInForce = TimeInForce.day,
        idempotency_key: str | None = None,
        decision: dict | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> Order:
        """Validate and submit order to OMS, reserving cash for BUY orders."""
        corr_id = correlation_id or uuid.uuid4()

        # 1. Idempotency Check
        if idempotency_key:
            existing = self._db.execute(
                select(Order).where(Order.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing:
                raise DuplicateIdempotencyKeyError(idempotency_key, existing.id)

        # 2. Basic Validations
        portfolio = self._db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        instrument = self._db.execute(
            select(Instrument).where(Instrument.id == instrument_id)
        ).scalar_one_or_none()
        if instrument is None:
            raise InstrumentNotFoundError(instrument_id)

        qty = _quantize(quantity)
        if qty <= Decimal("0.0000"):
            raise InvalidOrderQuantityError(qty, "Quantity must be greater than zero.")

        l_price = _quantize(limit_price) if limit_price is not None else None
        s_price = _quantize(stop_price) if stop_price is not None else None

        if order_type in (OrderType.limit, OrderType.stop_limit):
            if l_price is None or l_price <= Decimal("0.0000"):
                raise InvalidOrderPriceError(l_price, "Limit price required for LIMIT order.")

        if order_type in (OrderType.stop, OrderType.stop_limit):
            if s_price is None or s_price <= Decimal("0.0000"):
                raise InvalidOrderPriceError(s_price, "Stop price required for STOP order.")

        # 3. Create Order in CREATED status
        order = Order(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            side=side,
            order_type=order_type,
            product_type=product_type,
            time_in_force=time_in_force,
            quantity=qty,
            filled_quantity=Decimal("0.0000"),
            limit_price=l_price,
            stop_price=s_price,
            status=OrderStatus.created,
            idempotency_key=idempotency_key,
        )
        self._db.add(order)
        self._db.flush()

        # Create Explainability Decision record if provided
        if decision:
            order_decision = OrderDecision(
                order_id=order.id,
                model_confidence=Decimal(str(decision["model_confidence"])) if decision.get("model_confidence") is not None else Decimal("1.0"),
                expected_return=Decimal(str(decision["expected_return"])) if decision.get("expected_return") is not None else None,
                risk_reward_ratio=Decimal(str(decision["risk_reward_ratio"])) if decision.get("risk_reward_ratio") is not None else None,
                market_regime=decision.get("market_regime"),
                entry_reason=decision.get("entry_reason", "Manual or strategy signal"),
                exit_reason=decision.get("exit_reason"),
                summary=decision.get("summary", "Order submitted to OMS"),
                raw_signals=decision.get("raw_signals"),
            )
            self._db.add(order_decision)
            self._db.flush()

        evt_created = OrderCreatedEvent(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            payload={
                "order_id": str(order.id),
                "portfolio_id": str(order.portfolio_id),
                "instrument_id": str(order.instrument_id),
                "side": side.value,
                "order_type": order_type.value,
                "quantity": str(qty),
                "limit_price": str(l_price) if l_price else None,
            },
        )
        self._audit.record_event(evt_created)

        # 4. State Machine: created -> validated
        OrderStateMachine.transition(order, OrderStatus.validated)
        evt_val = OrderValidatedEvent(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            causation_id=evt_created.event_id,
        )
        self._audit.record_event(evt_val)

        # 5. Mandatory Pre-Trade Risk Gate (ADR 0010)
        risk_verdict = self._risk_service.evaluate_order(db=self._db, order=order)
        if risk_verdict.decision == RiskDecision.blocked:
            reject_reason = f"Risk check blocked ({risk_verdict.blocking_rule}): {risk_verdict.reason}"
            OrderStateMachine.transition(order, OrderStatus.rejected, reason=reject_reason)
            evt_rej = OrderRejectedEvent(
                aggregate_id=order.id,
                aggregate_version=order.version,
                correlation_id=corr_id,
                causation_id=evt_val.event_id,
                payload={"reason": reject_reason, "blocking_rule": risk_verdict.blocking_rule},
            )
            self._audit.record_event(evt_rej)
            self._db.flush()
            return order

        # 6. Buying Power Check & Cash Reservation (for BUY)
        if side == OrderSide.buy:
            ref_price = l_price or Decimal("1000.0000")  # Default buffer if market
            est_costs = self._cost_engine.calculate_cost(
                side=OrderSide.buy,
                product_type=product_type,
                exchange=instrument.exchange,
                quantity=qty,
                price=ref_price,
                profile_name=self._cost_engine.default_profile_name,
            )
            required_cash = _quantize((qty * ref_price) + est_costs.total_charges)
            order.reserved_cash = required_cash
            evt_res = self._ledger.reserve_buying_power(
                portfolio_id=portfolio_id,
                amount=required_cash,
                order_id=order.id,
                correlation_id=corr_id,
            )
            self._audit.record_event(evt_res)

        # 7. State Machine: validated -> accepted -> pending
        OrderStateMachine.transition(order, OrderStatus.accepted)
        evt_acc = OrderAcceptedEvent(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            causation_id=evt_val.event_id,
        )
        self._audit.record_event(evt_acc)

        OrderStateMachine.transition(order, OrderStatus.pending)
        evt_pend = OrderPendingEvent(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            causation_id=evt_acc.event_id,
        )
        self._audit.record_event(evt_pend)

        self._db.flush()
        return order

    def execute_order(
        self,
        order_id: uuid.UUID,
        market_price: Decimal,
        exchange: Exchange = Exchange.NSE,
        fill_quantity: Decimal | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> Fill | None:
        """Simulate and execute pending order against market price."""
        corr_id = correlation_id or uuid.uuid4()
        order = self._db.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise OrderNotFoundError(order_id)

        if not OrderStateMachine.is_active(order.status):
            return None

        m_price = _quantize(market_price)
        fill_res = self._simulator.evaluate_execution(
            order=order,
            market_price=m_price,
            exchange=exchange,
            fill_quantity=fill_quantity,
        )
        if fill_res is None:
            return None

        # 1. Create Fill record
        fill_seq = len(order.fills) + 1 if order.fills else 1
        fill = Fill(
            order_id=order.id,
            portfolio_id=order.portfolio_id,
            instrument_id=order.instrument_id,
            fill_sequence=fill_seq,
            quantity=fill_res.quantity,
            price=fill_res.price,
            slippage=fill_res.slippage,
            brokerage=fill_res.costs.brokerage,
            stt=fill_res.costs.stt,
            exchange_charges=fill_res.costs.exchange_charges,
            gst=fill_res.costs.gst,
            stamp_duty=fill_res.costs.stamp_duty,
            sebi_charges=fill_res.costs.sebi_charges,
            total_charges=fill_res.costs.total_charges,
            filled_at=fill_res.filled_at,
        )
        self._db.add(fill)
        self._db.flush()

        # 2. Update Order Quantities and Average Fill Price
        old_filled = order.filled_quantity
        new_filled = old_filled + fill.quantity
        old_cost = old_filled * (order.avg_fill_price or Decimal("0.0000"))
        new_avg = (old_cost + (fill.quantity * fill.price)) / new_filled

        order.filled_quantity = _quantize(new_filled)
        order.avg_fill_price = _quantize(new_avg)

        # 3. Transition Order State
        is_complete = order.filled_quantity >= order.quantity
        target_status = OrderStatus.filled if is_complete else OrderStatus.partial
        OrderStateMachine.transition(order, target_status)

        # 4. Settle Cash in Ledger
        turnover = fill.quantity * fill.price
        if order.side == OrderSide.buy:
            # Release proportional or full reserved buying power for this specific order
            if is_complete:
                rel_amount = order.reserved_cash
            else:
                prop_ratio = fill.quantity / order.quantity
                rel_amount = min(order.reserved_cash, _quantize(prop_ratio * order.reserved_cash))

            if rel_amount > Decimal("0.0000"):
                order.reserved_cash -= rel_amount
                evt_rel = self._ledger.release_buying_power(
                    portfolio_id=order.portfolio_id,
                    amount=rel_amount,
                    order_id=order.id,
                    correlation_id=corr_id,
                )
                self._audit.record_event(evt_rel)

            # Debit principal + charges
            _, e1 = self._ledger.record_transaction(
                portfolio_id=order.portfolio_id,
                txn_type=TxnType.buy_fill,
                amount=-turnover,
                related_order_id=order.id,
                related_fill_id=fill.id,
                reference_type="buy_execution",
                description=f"Buy {fill.quantity} units at {fill.price}",
                correlation_id=corr_id,
            )
            self._audit.record_event(e1)
        else:
            # Credit principal
            _, e1 = self._ledger.record_transaction(
                portfolio_id=order.portfolio_id,
                txn_type=TxnType.sell_fill,
                amount=turnover,
                related_order_id=order.id,
                related_fill_id=fill.id,
                reference_type="sell_execution",
                description=f"Sell {fill.quantity} units at {fill.price}",
                correlation_id=corr_id,
            )
            self._audit.record_event(e1)

        # Record itemized statutory charges in ledger
        if fill.total_charges > Decimal("0.0000"):
            _, e_fee = self._ledger.record_transaction(
                portfolio_id=order.portfolio_id,
                txn_type=TxnType.brokerage,
                amount=-fill.total_charges,
                related_order_id=order.id,
                related_fill_id=fill.id,
                reference_type="statutory_charges",
                description=f"Charges: brokerage={fill.brokerage}, stt={fill.stt}, exch={fill.exchange_charges}, gst={fill.gst}, stamp={fill.stamp_duty}, sebi={fill.sebi_charges}",
                correlation_id=corr_id,
            )
            self._audit.record_event(e_fee)

        # 5. Apply Fill to Positions & FIFO Lots
        _, pos_events = self._positions.apply_fill(
            fill=fill,
            side=order.side,
            product_type=order.product_type,
            correlation_id=corr_id,
        )
        for pe in pos_events:
            self._audit.record_event(pe)

        # 6. Emit Order Fill Event
        evt_fill_cls = OrderFilledEvent if is_complete else OrderPartiallyFilledEvent
        evt_fill = evt_fill_cls(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            payload={
                "order_id": str(order.id),
                "fill_id": str(fill.id),
                "filled_quantity": str(fill.quantity),
                "fill_price": str(fill.price),
                "total_charges": str(fill.total_charges),
                "status": order.status.value,
            },
        )
        self._audit.record_event(evt_fill)

        self._db.flush()
        return fill

    def cancel_order(
        self,
        order_id: uuid.UUID,
        reason: str = "User requested cancellation",
        correlation_id: uuid.UUID | None = None,
    ) -> Order:
        """Cancel an active order and release reserved buying power."""
        corr_id = correlation_id or uuid.uuid4()
        order = self._db.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise OrderNotFoundError(order_id)

        if not OrderStateMachine.is_cancellable(order.status):
            raise OrderNotCancellableError(order.id, order.status.value)

        # Release reserved cash if BUY order
        if order.side == OrderSide.buy and order.reserved_cash > Decimal("0.0000"):
            evt_rel = self._ledger.release_buying_power(
                portfolio_id=order.portfolio_id,
                amount=order.reserved_cash,
                order_id=order.id,
                correlation_id=corr_id,
            )
            self._audit.record_event(evt_rel)
            order.reserved_cash = Decimal("0.0000")

        OrderStateMachine.transition(order, OrderStatus.cancelled, reason=reason)
        evt_canc = OrderCancelledEvent(
            aggregate_id=order.id,
            aggregate_version=order.version,
            correlation_id=corr_id,
            payload={"order_id": str(order.id), "reason": reason},
        )
        self._audit.record_event(evt_canc)

        self._db.flush()
        return order

    def get_portfolio_summary(
        self,
        portfolio_id: uuid.UUID,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
    ) -> PortfolioSummary:
        """Calculate complete financial overview and net liquidation value."""
        portfolio = self._db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        stmt = select(Position).where(Position.portfolio_id == portfolio_id)
        positions = list(self._db.execute(stmt).scalars().all())

        prices = current_prices or {}
        invested_capital = Decimal("0.0000")
        market_value = Decimal("0.0000")
        total_realized = Decimal("0.0000")
        total_unrealized = Decimal("0.0000")
        open_count = 0

        for pos in positions:
            total_realized += pos.realized_pnl
            if pos.status == PositionStatus.open and pos.quantity > Decimal("0.0000"):
                open_count += 1
                cost = pos.quantity * pos.avg_entry_price
                invested_capital += cost
                cur_price = prices.get(pos.instrument_id, pos.current_price or pos.avg_entry_price)
                val = pos.quantity * cur_price
                market_value += val
                total_unrealized += (val - cost)

        total_val = portfolio.cash_balance + market_value
        available_bp = portfolio.cash_balance - portfolio.reserved_cash

        return PortfolioSummary(
            portfolio_id=portfolio.id,
            name=portfolio.name,
            mode=portfolio.mode.value,
            base_currency=portfolio.base_currency,
            initial_capital=portfolio.initial_capital,
            cash_balance=_quantize(portfolio.cash_balance),
            reserved_cash=_quantize(portfolio.reserved_cash),
            available_buying_power=_quantize(available_bp),
            invested_capital=_quantize(invested_capital),
            open_positions_market_value=_quantize(market_value),
            portfolio_total_value=_quantize(total_val),
            total_realized_pnl=_quantize(total_realized),
            total_unrealized_pnl=_quantize(total_unrealized),
            open_positions_count=open_count,
        )
