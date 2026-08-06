"""Strategy Registry, Versioning, and Dynamic Instantiation Engine."""
import logging
from typing import Any, Type
import uuid

from app.domains.strategies.base import BaseStrategy
from app.domains.strategies.exceptions import (
    DuplicateStrategyError,
    StrategyNotFoundError,
    StrategyVersionMismatchError,
)
from app.domains.strategies.schemas import StrategyMetadata

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Central registry for institutional strategy discovery, versioning, and lifecycle management."""

    _strategies: dict[str, dict[str, Type[BaseStrategy]]] = {}  # strategy_id -> {version -> class}
    _active_versions: dict[str, str] = {}  # strategy_id -> active_version

    @classmethod
    def register(cls, strategy_cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
        """Register a strategy class in the registry."""
        strategy_id = strategy_cls.strategy_id
        version = strategy_cls.version

        if strategy_id not in cls._strategies:
            cls._strategies[strategy_id] = {}

        if version in cls._strategies[strategy_id]:
            # Replace or raise if duplicate registered
            logger.info(f"Updating strategy registration: {strategy_id} v{version}")

        cls._strategies[strategy_id][version] = strategy_cls
        cls._active_versions[strategy_id] = version
        return strategy_cls

    @classmethod
    def get_strategy_class(cls, strategy_id: str, version: str | None = None) -> Type[BaseStrategy]:
        """Retrieve the strategy class for a given ID and version."""
        if strategy_id not in cls._strategies:
            raise StrategyNotFoundError(strategy_id)

        versions = cls._strategies[strategy_id]
        target_version = version or cls._active_versions.get(strategy_id)

        if target_version not in versions:
            raise StrategyVersionMismatchError(
                strategy_id=strategy_id,
                expected_version=target_version or "latest",
                found_version=f"Available: {list(versions.keys())}",
            )

        return versions[target_version]

    @classmethod
    def create_instance(
        cls,
        strategy_id: str,
        params: dict[str, Any] | None = None,
        version: str | None = None,
        parameter_snapshot_id: uuid.UUID | None = None,
    ) -> BaseStrategy:
        """Instantiate a registered strategy with validated parameters."""
        strategy_cls = cls.get_strategy_class(strategy_id, version)
        return strategy_cls(params=params, parameter_snapshot_id=parameter_snapshot_id)

    @classmethod
    def list_strategies(cls) -> list[StrategyMetadata]:
        """List metadata for all active registered strategies."""
        metadata_list = []
        for strategy_id, versions in cls._strategies.items():
            active_ver = cls._active_versions.get(strategy_id)
            if active_ver and active_ver in versions:
                strat_cls = versions[active_ver]
                metadata_list.append(strat_cls.get_metadata())
        return metadata_list

    @classmethod
    def get_metadata(cls, strategy_id: str, version: str | None = None) -> StrategyMetadata:
        """Get metadata for a specific strategy."""
        strat_cls = cls.get_strategy_class(strategy_id, version)
        return strat_cls.get_metadata()

    @classmethod
    def set_active_version(cls, strategy_id: str, version: str) -> None:
        """Hot-swap the active version for a strategy ID."""
        if strategy_id not in cls._strategies:
            raise StrategyNotFoundError(strategy_id)
        if version not in cls._strategies[strategy_id]:
            raise StrategyVersionMismatchError(strategy_id, version, f"Available: {list(cls._strategies[strategy_id].keys())}")
        cls._active_versions[strategy_id] = version

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (useful for test isolation)."""
        cls._strategies.clear()
        cls._active_versions.clear()


def register_strategy(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """Decorator to automatically register strategy classes."""
    return StrategyRegistry.register(cls)
