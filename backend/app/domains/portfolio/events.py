"""Domain Events for Portfolio Construction and Signal Arbitration Engine."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioConstructionStartedEvent:
    """Emitted when portfolio construction evaluation begins."""
    plan_id: uuid.UUID
    portfolio_id: uuid.UUID
    timestamp: datetime
    raw_signal_count: int


@dataclass(frozen=True)
class SignalArbitrationCompletedEvent:
    """Emitted when multi-signal conflict resolution completes."""
    plan_id: uuid.UUID
    portfolio_id: uuid.UUID
    timestamp: datetime
    instruments_processed: int
    conflicts_resolved: int


@dataclass(frozen=True)
class CandidateOrdersGeneratedEvent:
    """Emitted when final candidate orders have been generated and sized."""
    plan_id: uuid.UUID
    portfolio_id: uuid.UUID
    timestamp: datetime
    candidate_order_count: int
    total_allocated_notional: Decimal
    reserve_cash: Decimal
