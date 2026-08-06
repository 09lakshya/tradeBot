"""Strategy Evaluation Service, Audit Logging, and Lifecycle Management."""
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy.orm import Session

from app.domains.backtest.data_feed import HistoricalBar, PointInTimeDataFeed
from app.domains.strategies.base import BaseStrategy, StrategyContext
from app.domains.strategies.enums import StrategyStatus
from app.domains.strategies.exceptions import (
    StrategyExecutionError,
    StrategyNotFoundError,
    StrategyValidationError,
)
from app.domains.strategies.models import (
    StrategyModel,
    StrategyParameterSnapshotModel,
    StrategySignalModel,
)
from app.domains.strategies.registry import StrategyRegistry
from app.domains.strategies.schemas import (
    ParameterSnapshotCreate,
    StrategyCreate,
    StrategyMetadata,
    StrategyUpdate,
    TradingSignal,
)

logger = logging.getLogger(__name__)


class StrategyService:
    """Core orchestration service for strategy lifecycle, evaluation, and signal persistence."""

    def __init__(self, db: Session | None = None):
        self.db = db

    def register_or_update_strategy_in_db(self, metadata: StrategyMetadata) -> StrategyModel | None:
        """Ensure strategy metadata is persisted in the database."""
        if not self.db:
            return None

        strategy_record = (
            self.db.query(StrategyModel)
            .filter(StrategyModel.strategy_id == metadata.strategy_id)
            .first()
        )

        if not strategy_record:
            strategy_record = StrategyModel(
                id=uuid.uuid4(),
                strategy_id=metadata.strategy_id,
                name=metadata.name,
                version=metadata.version,
                author=metadata.author,
                description=metadata.description,
                category=metadata.category,
                is_active=True,
                metadata_json={
                    "default_parameters": metadata.default_parameters,
                    "parameter_schema": metadata.parameter_schema,
                    "required_lookback": metadata.required_lookback,
                    "min_history_required": metadata.min_history_required,
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(strategy_record)
            self.db.commit()
            self.db.refresh(strategy_record)
        else:
            strategy_record.version = metadata.version
            strategy_record.name = metadata.name
            strategy_record.description = metadata.description
            strategy_record.default_parameters = metadata.default_parameters
            strategy_record.parameter_schema = metadata.parameter_schema
            strategy_record.required_lookback = metadata.required_lookback
            strategy_record.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(strategy_record)

        return strategy_record

    def create_parameter_snapshot(
        self,
        strategy_id: str,
        parameters: dict[str, Any],
        description: str | None = None,
        created_by: str = "system",
    ) -> StrategyParameterSnapshotModel:
        """Create an immutable, versioned parameter snapshot for reproducible execution."""
        # Verify strategy exists
        strat_cls = StrategyRegistry.get_strategy_class(strategy_id)
        validated_params = strat_cls.validate_parameters(parameters)

        snapshot = StrategyParameterSnapshotModel(
            id=uuid.uuid4(),
            strategy_id=strategy_id,
            version=strat_cls.version,
            parameters=validated_params,
            description=description,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )

        if self.db:
            self.db.add(snapshot)
            self.db.commit()
            self.db.refresh(snapshot)

        return snapshot

    def evaluate_bar(
        self,
        strategy: BaseStrategy,
        bar: HistoricalBar,
        context: StrategyContext,
        persist_signals: bool = False,
    ) -> list[TradingSignal]:
        """Pure, fail-safe execution of a strategy on a single market bar."""
        try:
            signals = strategy.on_bar(bar, context)
        except Exception as e:
            logger.error(f"Strategy {strategy.strategy_id} failed on bar {bar.timestamp}: {e}", exc_info=True)
            raise StrategyExecutionError(strategy.strategy_id, str(e)) from e

        if persist_signals and self.db and signals:
            self.persist_signals(signals)

        return signals

    def persist_signals(self, signals: list[TradingSignal]) -> list[StrategySignalModel]:
        """Persist generated trading signals to the database for auditability and explainability."""
        if not self.db:
            return []

        models = []
        for s in signals:
            model = StrategySignalModel(
                id=s.signal_id,
                strategy_id=s.strategy_id,
                strategy_version=s.strategy_version,
                parameter_snapshot_id=s.parameter_snapshot_id,
                instrument_id=s.instrument_id,
                symbol=s.symbol,
                timestamp=s.timestamp,
                signal_type=s.signal_type.value,
                direction=s.direction.value,
                confidence=s.confidence,
                target_quantity=s.target_quantity,
                target_weight=s.target_weight,
                entry_price=s.entry_price,
                stop_loss=s.stop_loss,
                take_profit=s.take_profit,
                risk_reward_ratio=s.risk_reward_ratio,
                expected_holding_period=s.expected_holding_period,
                signal_expiry=s.signal_expiry,
                generation_time=s.generation_time,
                market_regime=s.market_regime.value,
                supporting_indicators=s.supporting_indicators,
                human_readable_explanation=s.human_readable_explanation,
                metadata_payload=s.metadata,
            )
            models.append(model)
            self.db.add(model)

        self.db.commit()
        return models

    def list_strategies(self) -> list[StrategyMetadata]:
        """Discover all strategies registered in the system."""
        return StrategyRegistry.list_strategies()

    def get_strategy(self, strategy_id: str, version: str | None = None) -> StrategyMetadata:
        """Get strategy metadata by ID."""
        return StrategyRegistry.get_metadata(strategy_id, version)

    def instantiate_strategy(
        self,
        strategy_id: str,
        parameters: dict[str, Any] | None = None,
        parameter_snapshot_id: uuid.UUID | None = None,
        version: str | None = None,
    ) -> BaseStrategy:
        """Instantiate a strategy instance ready for execution."""
        return StrategyRegistry.create_instance(
            strategy_id=strategy_id,
            params=parameters,
            version=version,
            parameter_snapshot_id=parameter_snapshot_id,
        )
