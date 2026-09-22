"""Deterministic Event-Driven Backtest Engine reusing production OMS, Risk Engine, and Cost Model."""
import heapq
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.backtest.enums import EventPriority
from app.domains.backtest.events import MarketBarEvent, PriorityEvent
from app.domains.backtest.slippage import BaseSlippageModel, FixedBpsSlippage
from app.domains.backtest.strategy_adapter import (
    BaseBacktestStrategy,
    StrategyContext,
    StrategySignal,
)
from app.domains.risk.service import RiskService
from app.domains.trading.clock import ReplayClock
from app.domains.trading.enums import OrderSide, OrderStatus
from app.domains.trading.models import Order
from app.domains.trading.service import TradingService


def _quantize(val: Decimal | float) -> Decimal:
    if isinstance(val, float):
        val = Decimal(str(round(val, 4)))
    return val.quantize(Decimal("0.0001"))


@dataclass
class BacktestTradeRecord:
    """Detailed explainable trade record."""
    order_id: uuid.UUID
    fill_id: uuid.UUID
    signal_id: uuid.UUID | None
    strategy_id: str
    instrument_id: uuid.UUID
    symbol: str
    side: OrderSide
    quantity: Decimal
    execution_price: Decimal
    slippage: Decimal
    total_fees: Decimal
    fee_breakdown: dict[str, Any]
    realized_pnl: Decimal
    risk_verdict_token: str | None
    executed_at: datetime


@dataclass
class EquitySnapshotPoint:
    """Point-in-time portfolio equity snapshot."""
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    drawdown_pct: Decimal
    high_water_mark: Decimal


@dataclass
class BacktestExecutionResult:
    """Full execution output of a backtest run."""
    portfolio_id: uuid.UUID
    initial_capital: Decimal
    ending_capital: Decimal
    total_return_pct: Decimal
    equity_curve: list[EquitySnapshotPoint]
    trades: list[BacktestTradeRecord]
    rejected_orders_count: int = 0
    total_bars_processed: int = 0


class BacktestEngine:
    """The central single-threaded deterministic event loop for historical backtesting.
    Strictly reuses production TradingService and RiskService without simulator drift.
    """

    def __init__(
        self,
        db: Session,
        clock: ReplayClock,
        trading_service: TradingService,
        risk_service: RiskService,
        data_feed: PointInTimeDataFeed,
        strategy: BaseBacktestStrategy,
        slippage_model: BaseSlippageModel | None = None,
        random_seed: int = 42,
    ):
        self.db = db
        self.clock = clock
        self.trading = trading_service
        self.risk = risk_service
        self.data_feed = data_feed
        self.strategy = strategy
        self.slippage_model = slippage_model or FixedBpsSlippage()
        self.random_seed = random_seed

        # Internal state
        self._event_queue: list[PriorityEvent] = []
        self._sequence_counter = 0
        self._pending_orders_by_instrument: dict[uuid.UUID, list[tuple[Order, StrategySignal]]] = {}
        self._trades: list[BacktestTradeRecord] = []
        self._equity_curve: list[EquitySnapshotPoint] = []
        self._high_water_mark = Decimal("0.0000")
        self._rejected_orders_count = 0
        self._total_bars_processed = 0

    def _enqueue_event(self, event: PriorityEvent) -> None:
        """Enqueue an event with deterministic sequence counter for tie-breaking."""
        heapq.heappush(self._event_queue, event)

    def run(self, portfolio_id: uuid.UUID) -> BacktestExecutionResult:
        """Execute backtest event loop from first to last bar."""
        initial_summary = self.trading.get_portfolio_summary(portfolio_id)
        initial_capital = initial_summary.portfolio_total_value
        self._high_water_mark = initial_capital

        # Initialize event queue with all historical bars
        all_bars = list(self.data_feed.iter_all_bars_chronologically())
        for bar in all_bars:
            self._sequence_counter += 1
            evt = MarketBarEvent(
                timestamp=bar.timestamp,
                priority=EventPriority.MARKET_DATA.value,
                sequence_id=self._sequence_counter,
                instrument_id=bar.instrument_id,
                symbol=bar.symbol,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                timeframe=bar.timeframe,
            )
            self._enqueue_event(evt)

        # Main Event Loop
        while self._event_queue:
            event = heapq.heappop(self._event_queue)

            # Advance simulation clock
            if isinstance(self.clock, ReplayClock):
                self.clock.step_to(event.timestamp)
            elif hasattr(self.clock, "set_time"):
                self.clock.set_time(event.timestamp)

            if isinstance(event, MarketBarEvent):
                self._process_bar_event(event, portfolio_id)

        # Final EOD Snapshot & Reconciliation
        final_summary = self.trading.get_portfolio_summary(portfolio_id)
        ending_capital = final_summary.portfolio_total_value
        total_return_pct = (
            ((ending_capital - initial_capital) / initial_capital * Decimal("100.0"))
            if initial_capital > Decimal("0.0")
            else Decimal("0.0000")
        )

        return BacktestExecutionResult(
            portfolio_id=portfolio_id,
            initial_capital=initial_capital,
            ending_capital=ending_capital,
            total_return_pct=_quantize(total_return_pct),
            equity_curve=self._equity_curve,
            trades=self._trades,
            rejected_orders_count=self._rejected_orders_count,
            total_bars_processed=self._total_bars_processed,
        )

    def _process_bar_event(self, bar_evt: MarketBarEvent, portfolio_id: uuid.UUID) -> None:
        """Process an individual market bar:
        1. Fill orders submitted on previous bar (bar t-1) at this bar's Open +- slippage.
        2. Update mark-to-market position valuation and snapshot equity.
        3. Invoke strategy on_bar() to generate signals on bar t Close.
        4. Submit signals as orders through OMS & Risk Gate (held for bar t+1 execution).
        """
        self._total_bars_processed += 1
        inst_id = bar_evt.instrument_id

        # 1. Fill Pending Orders from previous bar at NEXT BAR OPEN (No Lookahead)
        if inst_id in self._pending_orders_by_instrument:
            pending_items = self._pending_orders_by_instrument.pop(inst_id)
            for order, signal in pending_items:
                self._execute_pending_order(order, signal, bar_evt)

        # 2. Mark-to-Market Valuation & Equity Snapshot
        # Update current price in PositionManager
        pos = self.trading.positions.get_position(portfolio_id, inst_id)
        if pos and pos.status.value == "open":
            pos.current_price = bar_evt.close
            pos.unrealized_pnl = _quantize((bar_evt.close - pos.avg_entry_price) * pos.quantity)
            self.db.flush()

        summary = self.trading.get_portfolio_summary(portfolio_id)
        current_equity = summary.portfolio_total_value
        if current_equity > self._high_water_mark:
            self._high_water_mark = current_equity

        dd_pct = (
            ((self._high_water_mark - current_equity) / self._high_water_mark * Decimal("100.0"))
            if self._high_water_mark > Decimal("0.0")
            else Decimal("0.0000")
        )

        self._equity_curve.append(
            EquitySnapshotPoint(
                timestamp=bar_evt.timestamp,
                equity=current_equity,
                cash=summary.cash_balance,
                positions_value=summary.open_positions_market_value,
                drawdown_pct=_quantize(dd_pct),
                high_water_mark=self._high_water_mark,
            )
        )

        # 3. Strategy Evaluation on Current Bar
        positions_dict = {
            p.instrument_id: p.quantity
            for p in self.trading.positions.get_portfolio_positions(portfolio_id)
            if p.status.value == "open"
        }

        ctx = StrategyContext(
            portfolio_id=portfolio_id,
            current_time=bar_evt.timestamp,
            cash_balance=summary.cash_balance,
            current_equity=current_equity,
            positions=positions_dict,
            data_feed=self.data_feed,
        )

        hist_bar = HistoricalBar(
            instrument_id=bar_evt.instrument_id,
            symbol=bar_evt.symbol,
            timestamp=bar_evt.timestamp,
            open=bar_evt.open,
            high=bar_evt.high,
            low=bar_evt.low,
            close=bar_evt.close,
            volume=bar_evt.volume,
            timeframe=bar_evt.timeframe,
        )

        signals = self.strategy.on_bar(hist_bar, ctx)

        # 4. Submit Orders through OMS + Risk Gate (Next-bar execution)
        for sig in signals:
            try:
                order = self.trading.submit_order(
                    portfolio_id=portfolio_id,
                    instrument_id=sig.instrument_id,
                    side=sig.side,
                    order_type=sig.order_type,
                    quantity=sig.target_quantity,
                    limit_price=sig.limit_price or bar_evt.close,
                    product_type=sig.product_type,
                )
                if order.status == OrderStatus.accepted or order.status == OrderStatus.pending:
                    if inst_id not in self._pending_orders_by_instrument:
                        self._pending_orders_by_instrument[inst_id] = []
                    self._pending_orders_by_instrument[inst_id].append((order, sig))
                else:
                    self._rejected_orders_count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Order submission failed in backtest: %s", e)
                self._rejected_orders_count += 1

    def _execute_pending_order(
        self,
        order: Order,
        signal: StrategySignal,
        bar_evt: MarketBarEvent,
    ) -> None:
        """Execute fill with deterministic slippage at next bar open."""
        fill_price, slippage_amt = self.slippage_model.calculate_fill_price(
            base_price=bar_evt.open,
            side=order.side,
            quantity=order.quantity,
            bar_volume=bar_evt.volume,
            bar_high=bar_evt.high,
            bar_low=bar_evt.low,
            random_seed=self.random_seed,
            order_id=order.id,
        )

        try:
            # Execute fill via TradingService
            fill = self.trading.execute_order(
                order_id=order.id,
                market_price=fill_price,
            )
            if fill is None:
                self._rejected_orders_count += 1
                return

            # Record explainable trade log
            trade_rec = BacktestTradeRecord(
                order_id=order.id,
                fill_id=fill.id,
                signal_id=signal.signal_id,
                strategy_id=signal.strategy_id,
                instrument_id=order.instrument_id,
                symbol=bar_evt.symbol,
                side=order.side,
                quantity=fill.quantity,
                execution_price=fill.price,
                slippage=slippage_amt,
                total_fees=fill.total_charges,
                fee_breakdown={"total_charges": str(fill.total_charges)},
                realized_pnl=Decimal("0.0000"),  # Realized PnL is tracked on FIFO position closes
                risk_verdict_token=None,
                executed_at=bar_evt.timestamp,
            )
            self._trades.append(trade_rec)

            # Strategy fill callback
            self.strategy.on_fill({"order_id": order.id, "fill_id": fill.id, "price": fill.price}, None)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Order execution failed in backtest: %s", e, exc_info=True)
            # If execution fails (e.g. insufficient buying power at open), cancel order
            try:
                self.trading.cancel_order(order.id)
            except Exception:
                pass
            self._rejected_orders_count += 1
