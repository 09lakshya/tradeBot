"""Unit tests for the Immutable Audit Trail System."""
import uuid
from app.domains.platform.audit import AuditBuffer, AuditRecord, AuditTrailService


def test_audit_record_creation():
    rec = AuditRecord(
        actor="orchestrator",
        component="pipeline",
        action="order_submitted",
        entity_type="order",
        entity_id="ord-100",
        before_state={"status": "pending"},
        after_state={"status": "submitted"},
        metadata={"symbol": "INFY", "quantity": 10},
    )
    assert rec.actor == "orchestrator"
    assert rec.action == "order_submitted"
    assert rec.entity_id == "ord-100"
    assert rec.metadata["symbol"] == "INFY"


def test_audit_buffer_and_service():
    buf = AuditBuffer(capacity=5)
    svc = AuditTrailService(buffer=buf)

    r1 = svc.record("risk_engine", "risk", "risk_rejection", entity_id="cand-1", metadata={"reason": "max_drawdown"})
    r2 = svc.record("oms", "trading", "order_filled", entity_id="ord-2", metadata={"price": "2500.00"})
    r3 = svc.record("strategy", "strategies", "signal_generated", entity_id="sig-3", metadata={"strategy": "ema"})

    assert buf.count == 3
    history = svc.get_history()
    assert len(history) == 3
    assert history[0].action == "signal_generated"  # Most recent first

    filtered_risk = svc.get_history(component="risk")
    assert len(filtered_risk) == 1
    assert filtered_risk[0].action == "risk_rejection"

    filtered_actor = svc.get_history(actor="oms")
    assert len(filtered_actor) == 1
    assert filtered_actor[0].action == "order_filled"
