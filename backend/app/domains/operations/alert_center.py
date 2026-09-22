"""Operational Alert Center for Phase 10."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.domains.operations.models import AlertSeverity, OperationalAlert
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.alert_center")
DEFAULT_ALERT_DIR = Path("scratch/operational_alerts")


class OperationalAlertCenter:
    """Manages operational alerts for strategy degradation, high slippage, costs, drawdowns, and scheduler failures."""

    def __init__(self, alert_dir: Path = DEFAULT_ALERT_DIR) -> None:
        self.alert_dir = alert_dir
        self.alert_dir.mkdir(parents=True, exist_ok=True)
        self._alerts: dict[str, OperationalAlert] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def raise_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.warning,
        details: dict[str, Any] | None = None,
    ) -> OperationalAlert:
        """Constructs and registers an operational alert."""
        alert = OperationalAlert(
            severity=severity,
            alert_type=alert_type,
            title=title,
            message=message,
            details=details or {},
        )

        with self._lock:
            self._alerts[alert.alert_id] = alert
            self._persist_alert(alert)
            logger.warning("operational_alert_raised", alert_id=alert.alert_id, type=alert_type, title=title)

        return alert

    def resolve_alert(self, alert_id: str) -> OperationalAlert:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                raise KeyError(f"Alert {alert_id} not found")
            alert.resolved = True
            self._persist_alert(alert)
            logger.info("operational_alert_resolved", alert_id=alert_id)
            return alert

    def get_alert(self, alert_id: str) -> OperationalAlert | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def list_alerts(
        self,
        severity: AlertSeverity | None = None,
        alert_type: str | None = None,
        resolved: bool | None = None,
    ) -> list[OperationalAlert]:
        with self._lock:
            res = list(self._alerts.values())
            if severity:
                res = [a for a in res if a.severity == severity]
            if alert_type:
                res = [a for a in res if a.alert_type == alert_type]
            if resolved is not None:
                res = [a for a in res if a.resolved == resolved]
            return res

    def _persist_alert(self, alert: OperationalAlert) -> None:
        filepath = self.alert_dir / f"alert_{alert.alert_id}.json"
        filepath.write_text(alert.model_dump_json(indent=2), encoding="utf-8")

    def _load_persisted(self) -> None:
        for file in self.alert_dir.glob("alert_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                alert = OperationalAlert(**data)
                self._alerts[alert.alert_id] = alert
            except Exception as exc:
                logger.warning("alert_load_failed", file=str(file), error=str(exc))
