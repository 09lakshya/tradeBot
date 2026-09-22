"""Dynamic, Validated Runtime Configuration Management Service."""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domains.platform.logging import get_structured_logger

log = get_structured_logger("platform.config")


class PlatformRuntimeConfig(BaseModel):
    """Typed runtime configuration schema with strict domain validation."""
    max_active_orders: int = Field(default=100, ge=1, le=1000)
    cycle_interval_seconds: float = Field(default=60.0, ge=0.5, le=3600.0)
    max_single_order_pct: float = Field(default=0.05, gt=0.0, le=1.0)
    max_portfolio_leverage: float = Field(default=1.0, gt=0.0, le=5.0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=50)
    circuit_breaker_recovery_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    retry_max_attempts: int = Field(default=3, ge=0, le=10)
    logging_level: str = Field(default="INFO")
    kill_switch_enabled: bool = Field(default=False)
    enable_paper_fill_simulation: bool = Field(default=True)
    version: int = Field(default=1)
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("logging_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid logging_level '{v}'. Must be one of {valid}")
        return v.upper()


class RuntimeConfigService:
    """Thread-safe dynamic configuration manager allowing safe runtime adjustments without restarts."""

    def __init__(self, initial_config: PlatformRuntimeConfig | None = None) -> None:
        self._config = initial_config or PlatformRuntimeConfig()
        self._listeners: list[Callable[[PlatformRuntimeConfig], None]] = []
        self._lock = threading.Lock()

    def get_config(self) -> PlatformRuntimeConfig:
        """Returns a snapshot of the current active configuration."""
        with self._lock:
            return self._config.model_copy()

    def update_config(self, updates: dict[str, Any]) -> PlatformRuntimeConfig:
        """Applies partial validated updates, increments version, and notifies listeners."""
        with self._lock:
            current_dict = self._config.model_dump()
            current_dict.update(updates)
            current_dict["version"] = self._config.version + 1
            current_dict["updated_at"] = datetime.now(UTC).isoformat()

            new_config = PlatformRuntimeConfig.model_validate(current_dict)
            self._config = new_config

            log.info(
                "runtime_config_updated",
                version=new_config.version,
                updated_fields=list(updates.keys()),
            )

        # Notify change listeners outside the lock
        for listener in self._listeners:
            try:
                listener(new_config)
            except Exception as exc:
                log.error("runtime_config_listener_error", error=str(exc))

        return new_config

    def register_listener(self, callback: Callable[[PlatformRuntimeConfig], None]) -> None:
        """Registers a callback invoked whenever the configuration is hot-reloaded."""
        with self._lock:
            self._listeners.append(callback)


global_runtime_config_service = RuntimeConfigService()
