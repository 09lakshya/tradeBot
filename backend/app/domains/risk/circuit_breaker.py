"""Kill Switch and Circuit Breaker State Management."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.risk.enums import BreakerState, ScopeType
from app.domains.risk.models import CircuitBreaker, KillSwitch
from app.domains.trading.clock import Clock


class KillSwitchManager:
    """Manages emergency stop states across Global, Portfolio, and Symbol scopes."""

    def __init__(self, db: Session, clock: Clock):
        self.db = db
        self.clock = clock

    def trip(
        self,
        scope: ScopeType,
        scope_id: str | None,
        reason: str,
        activated_by: str = "system",
    ) -> KillSwitch:
        """Activate the kill switch for the specified scope."""
        now = self.clock.now()
        ks = self.db.execute(
            select(KillSwitch).where(
                KillSwitch.scope == scope,
                KillSwitch.scope_id == scope_id,
            )
        ).scalar_one_or_none()

        if not ks:
            ks = KillSwitch(
                scope=scope,
                scope_id=scope_id,
                is_active=True,
                reason=reason,
                activated_by=activated_by,
                activated_at=now,
            )
            self.db.add(ks)
        else:
            ks.is_active = True
            ks.reason = reason
            ks.activated_by = activated_by
            ks.activated_at = now
            ks.reset_at = None
            ks.reset_by = None
            ks.reset_reason = None

        self.db.flush()
        return ks

    def reset(
        self,
        scope: ScopeType,
        scope_id: str | None,
        reset_reason: str,
        reset_by: str = "admin",
    ) -> KillSwitch | None:
        """Reset an active kill switch (audited)."""
        now = self.clock.now()
        ks = self.db.execute(
            select(KillSwitch).where(
                KillSwitch.scope == scope,
                KillSwitch.scope_id == scope_id,
            )
        ).scalar_one_or_none()

        if ks and ks.is_active:
            ks.is_active = False
            ks.reset_at = now
            ks.reset_by = reset_by
            ks.reset_reason = reset_reason
            self.db.flush()

        return ks

    def is_tripped(self, scope: ScopeType, scope_id: str | None) -> bool:
        """Check if kill switch is actively tripped for the given scope."""
        ks = self.db.execute(
            select(KillSwitch).where(
                KillSwitch.scope == scope,
                KillSwitch.scope_id == scope_id,
                KillSwitch.is_active == True,
            )
        ).scalar_one_or_none()
        return ks is not None


class CircuitBreakerManager:
    """Manages automatic cooloff and recovery state transitions for circuit breakers."""

    def __init__(self, db: Session, clock: Clock):
        self.db = db
        self.clock = clock

    def trip(
        self,
        scope: ScopeType,
        scope_id: str | None,
        reason: str,
        cooloff_seconds: int = 300,
    ) -> CircuitBreaker:
        """Trip circuit breaker and set cooldown timer."""
        now = self.clock.now()
        cb = self.db.execute(
            select(CircuitBreaker).where(
                CircuitBreaker.scope == scope,
                CircuitBreaker.scope_id == scope_id,
            )
        ).scalar_one_or_none()

        cooloff_until = now + timedelta(seconds=cooloff_seconds)

        if not cb:
            cb = CircuitBreaker(
                scope=scope,
                scope_id=scope_id,
                state=BreakerState.tripped,
                cooloff_until=cooloff_until,
                trip_count=1,
                last_tripped_at=now,
                reason=reason,
            )
            self.db.add(cb)
        else:
            cb.state = BreakerState.tripped
            cb.cooloff_until = cooloff_until
            cb.trip_count += 1
            cb.last_tripped_at = now
            cb.reason = reason

        self.db.flush()
        return cb

    def check_and_update(self, scope: ScopeType, scope_id: str | None) -> CircuitBreaker | None:
        """Advance tripped circuit breaker to half_open once cooldown expires."""
        now = self.clock.now()
        cb = self.db.execute(
            select(CircuitBreaker).where(
                CircuitBreaker.scope == scope,
                CircuitBreaker.scope_id == scope_id,
            )
        ).scalar_one_or_none()

        if cb and cb.state == BreakerState.tripped:
            if cb.cooloff_until and now >= cb.cooloff_until:
                cb.state = BreakerState.half_open
                self.db.flush()

        return cb

    def reset(self, scope: ScopeType, scope_id: str | None) -> CircuitBreaker | None:
        """Manually or automatically reset a circuit breaker back to armed state."""
        cb = self.db.execute(
            select(CircuitBreaker).where(
                CircuitBreaker.scope == scope,
                CircuitBreaker.scope_id == scope_id,
            )
        ).scalar_one_or_none()

        if cb:
            cb.state = BreakerState.armed
            cb.cooloff_until = None
            self.db.flush()

        return cb
