"""Enumerations for the Execution Orchestrator and Session Management domain."""
import enum


class SessionState(str, enum.Enum):
    """Indian Market (NSE/BSE) trading session states."""
    pre_open = "pre_open"                      # 09:00 - 09:08 IST: Order collection
    pre_open_matching = "pre_open_matching"    # 09:08 - 09:15 IST: Price discovery / matching
    regular_hours = "regular_hours"            # 09:15 - 15:30 IST: Continuous trading
    closing_auction = "closing_auction"        # 15:30 - 15:40 IST: Closing price discovery
    post_market = "post_market"                # 15:40 - 16:00 IST: Post-close order matching
    closed = "closed"                          # 16:00 - 09:00 IST / Weekends / Holidays


class PipelineStage(str, enum.Enum):
    """Stages in the integrated execution cycle pipeline."""
    session_validation = "session_validation"
    market_data_ingest = "market_data_ingest"
    strategy_evaluation = "strategy_evaluation"
    portfolio_construction = "portfolio_construction"
    risk_evaluation = "risk_evaluation"
    order_submission = "order_submission"
    execution_simulation = "execution_simulation"
    ledger_reconciliation = "ledger_reconciliation"
    invariant_verification = "invariant_verification"


class OrchestratorMode(str, enum.Enum):
    """Operational mode of the orchestrator."""
    paper = "paper"
    backtest = "backtest"
    live = "live"


class CycleStatus(str, enum.Enum):
    """Outcome status of an execution cycle."""
    success = "success"
    partial_failure = "partial_failure"
    failed = "failed"
    skipped_market_closed = "skipped_market_closed"


class InvariantStatus(str, enum.Enum):
    """Invariant validation result."""
    passed = "passed"
    failed = "failed"
    warning = "warning"


class EventType(str, enum.Enum):
    """Immutable domain event types published across the internal event bus."""
    market_data_updated = "MarketDataUpdated"
    strategy_evaluation_completed = "StrategyEvaluationCompleted"
    portfolio_construction_completed = "PortfolioConstructionCompleted"
    risk_evaluation_completed = "RiskEvaluationCompleted"
    order_submitted = "OrderSubmitted"
    order_filled = "OrderFilled"
    order_rejected = "OrderRejected"
    portfolio_updated = "PortfolioUpdated"
    session_started = "SessionStarted"
    session_ended = "SessionEnded"
    invariant_failed = "InvariantFailed"
