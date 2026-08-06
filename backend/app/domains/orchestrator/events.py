"""Typed immutable domain events for the Execution Orchestrator."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domains.orchestrator.enums import EventType, SessionState


class BaseOrchestratorEvent(BaseModel):
    """Immutable base class for all orchestrator domain events."""
    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "ExecutionOrchestrator"

    def to_dict(self) -> dict[str, Any]:
        """Converts event to serializable dictionary."""
        return self.model_dump(mode="json")


class MarketDataUpdatedEvent(BaseOrchestratorEvent):
    """Emitted when new market data snapshots are ingested."""
    event_type: EventType = EventType.market_data_updated
    instrument_count: int
    latest_timestamp: datetime


class StrategyEvaluationCompletedEvent(BaseOrchestratorEvent):
    """Emitted when all active strategies complete signal generation."""
    event_type: EventType = EventType.strategy_evaluation_completed
    signals_count: int
    strategy_ids: list[str]
    duration_ms: float


class PortfolioConstructionCompletedEvent(BaseOrchestratorEvent):
    """Emitted when portfolio construction produces a new plan and candidate orders."""
    event_type: EventType = EventType.portfolio_construction_completed
    plan_id: uuid.UUID
    candidate_orders_count: int
    total_equity: Decimal
    cash_allocated: Decimal


class RiskEvaluationCompletedEvent(BaseOrchestratorEvent):
    """Emitted when the pre-trade risk engine finishes evaluating candidate orders."""
    event_type: EventType = EventType.risk_evaluation_completed
    approved_count: int
    rejected_count: int
    circuit_breaker_active: bool = False


class OrderSubmittedEvent(BaseOrchestratorEvent):
    """Emitted when an order is submitted to the OMS."""
    event_type: EventType = EventType.order_submitted
    order_id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None = None


class OrderFilledEvent(BaseOrchestratorEvent):
    """Emitted when an order fill is executed in the paper trading simulator."""
    event_type: EventType = EventType.order_filled
    order_id: uuid.UUID
    fill_id: uuid.UUID
    fill_price: Decimal
    fill_quantity: Decimal
    commission: Decimal


class OrderRejectedEvent(BaseOrchestratorEvent):
    """Emitted when an order is rejected by risk or OMS."""
    event_type: EventType = EventType.order_rejected
    order_id: uuid.UUID
    reason: str


class PortfolioUpdatedEvent(BaseOrchestratorEvent):
    """Emitted when portfolio cash, equity, or positions are updated."""
    event_type: EventType = EventType.portfolio_updated
    portfolio_id: uuid.UUID
    cash_balance: Decimal
    total_equity: Decimal
    positions_count: int


class SessionStartedEvent(BaseOrchestratorEvent):
    """Emitted when a new market trading session begins."""
    event_type: EventType = EventType.session_started
    exchange: str
    session_state: SessionState
    session_date: str


class SessionEndedEvent(BaseOrchestratorEvent):
    """Emitted when a market trading session ends."""
    event_type: EventType = EventType.session_ended
    exchange: str
    session_state: SessionState
    session_date: str


class InvariantFailedEvent(BaseOrchestratorEvent):
    """Emitted when a continuous financial or state invariant check fails."""
    event_type: EventType = EventType.invariant_failed
    invariant_name: str
    discrepancy_details: dict[str, Any]
