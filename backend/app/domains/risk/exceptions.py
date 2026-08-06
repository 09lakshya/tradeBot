"""Risk Domain Typed Exceptions."""
import uuid


class RiskDomainError(Exception):
    """Base class for all domain exceptions originating from the Risk Engine."""

    def __init__(self, message: str, code: str = "RISK_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class RuleBlockedError(RiskDomainError):
    """Raised when an order is blocked by a specific pre-trade risk rule."""

    def __init__(
        self,
        rule_name: str,
        observed: str,
        threshold: str,
        detail: str,
    ):
        super().__init__(
            f"Risk rule '{rule_name}' blocked order: measured={observed}, threshold={threshold}. {detail}",
            code="RULE_BLOCKED",
        )
        self.rule_name = rule_name
        self.observed = observed
        self.threshold = threshold
        self.detail = detail


class KillSwitchTrippedError(RiskDomainError):
    """Raised when an order is submitted while a kill switch is active."""

    def __init__(self, scope: str, scope_id: str | None, reason: str | None):
        super().__init__(
            f"Kill switch active for scope '{scope}' (id={scope_id}): {reason or 'Emergency stop active'}",
            code="KILL_SWITCH_ACTIVE",
        )
        self.scope = scope
        self.scope_id = scope_id
        self.reason = reason


class CircuitBreakerTrippedError(RiskDomainError):
    """Raised when an order is submitted while a circuit breaker is in cool-off."""

    def __init__(self, scope: str, scope_id: str | None, cooloff_until: str | None, reason: str | None):
        super().__init__(
            f"Circuit breaker tripped for scope '{scope}' (id={scope_id}) until {cooloff_until}: {reason}",
            code="CIRCUIT_BREAKER_TRIPPED",
        )
        self.scope = scope
        self.scope_id = scope_id
        self.cooloff_until = cooloff_until
        self.reason = reason


class RiskLimitsNotFoundError(RiskDomainError):
    """Raised when risk limits configuration for a portfolio cannot be found."""

    def __init__(self, portfolio_id: uuid.UUID):
        super().__init__(
            f"Risk limits not configured for portfolio {portfolio_id}",
            code="RISK_LIMITS_NOT_FOUND",
        )
        self.portfolio_id = portfolio_id


class SnapshotUnavailableError(RiskDomainError):
    """Raised when a risk snapshot cannot be reliably constructed (fail-closed)."""

    def __init__(self, reason: str):
        super().__init__(
            f"Failed to build risk snapshot (failing closed): {reason}",
            code="SNAPSHOT_UNAVAILABLE",
        )
        self.reason = reason
