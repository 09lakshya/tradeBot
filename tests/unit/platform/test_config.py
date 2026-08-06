"""Unit tests for Dynamic Runtime Configuration."""
import pytest
from app.domains.platform.config import PlatformRuntimeConfig, RuntimeConfigService


def test_runtime_config_defaults_and_validation():
    cfg = PlatformRuntimeConfig()
    assert cfg.max_active_orders == 100
    assert cfg.cycle_interval_seconds == 60.0
    assert cfg.max_single_order_pct == 0.05
    assert cfg.kill_switch_enabled is False

    with pytest.raises(ValueError):
        PlatformRuntimeConfig(max_single_order_pct=1.5)  # > 1.0

    with pytest.raises(ValueError):
        PlatformRuntimeConfig(logging_level="INVALID_LEVEL")


def test_runtime_config_service_updates_and_listeners():
    svc = RuntimeConfigService()
    notified_versions = []

    def on_config_change(new_cfg: PlatformRuntimeConfig) -> None:
        notified_versions.append(new_cfg.version)

    svc.register_listener(on_config_change)

    updated = svc.update_config({"max_active_orders": 250, "logging_level": "DEBUG"})
    assert updated.version == 2
    assert updated.max_active_orders == 250
    assert updated.logging_level == "DEBUG"
    assert notified_versions == [2]

    # Current snapshot check
    snapshot = svc.get_config()
    assert snapshot.max_active_orders == 250
