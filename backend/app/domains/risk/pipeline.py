"""Pre-trade Risk Evaluation Pipeline with Fail-Closed Guarantees."""
import hashlib
import hmac
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime

from app.domains.risk.enums import RiskDecision
from app.domains.risk.rules import (
    BuyingPowerRule,
    CircuitBreakerRule,
    CorrelationLimitRule,
    DailyLossLimitRule,
    DrawdownLimitRule,
    ExposureLimitRule,
    KillSwitchRule,
    OrderRiskContext,
    PositionSizingRule,
    RateLimitRule,
    RiskRule,
    RuleResult,
    SanityRule,
)
from app.domains.risk.schemas import RiskVerdict, RuleEvaluationResult
from app.domains.risk.snapshot import RiskSnapshot

log = logging.getLogger(__name__)


class RiskPipeline:
    """Sequential pre-trade risk evaluation pipeline.

    Enforces all-must-pass semantics, fail-closed error handling,
    and deterministic verdict token generation.
    """

    def __init__(self, rules: Sequence[RiskRule] | None = None, secret_key: str = "tradebot-risk-secret"):
        self.rules: Sequence[RiskRule] = rules or (
            SanityRule(),
            KillSwitchRule(),
            CircuitBreakerRule(),
            BuyingPowerRule(),
            PositionSizingRule(),
            ExposureLimitRule(),
            CorrelationLimitRule(),
            DailyLossLimitRule(),
            DrawdownLimitRule(),
            RateLimitRule(),
        )
        self.secret_key = secret_key

    def _generate_verdict_token(
        self,
        order_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        decision: RiskDecision,
        timestamp: datetime,
    ) -> str:
        """Generate a deterministic HMAC signature for the risk verdict token."""
        message = f"{order_id}:{portfolio_id}:{decision.value}:{timestamp.isoformat()}".encode()
        return hmac.new(self.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def evaluate(self, order: OrderRiskContext, snapshot: RiskSnapshot) -> RiskVerdict:
        """Run order through the full risk pipeline with fail-closed safety."""
        rule_results: list[RuleEvaluationResult] = []

        try:
            for rule in self.rules:
                res: RuleResult = rule.evaluate(order, snapshot)
                rule_results.append(
                    RuleEvaluationResult(
                        rule=res.rule.value,
                        decision=res.decision,
                        observed_value=res.observed_value,
                        threshold_value=res.threshold_value,
                        detail=res.detail,
                    )
                )

                if res.decision == RiskDecision.blocked:
                    token = self._generate_verdict_token(
                        order.order_id, order.portfolio_id, RiskDecision.blocked, snapshot.timestamp
                    )
                    return RiskVerdict(
                        decision=RiskDecision.blocked,
                        verdict_token=token,
                        order_id=order.order_id,
                        portfolio_id=order.portfolio_id,
                        timestamp=snapshot.timestamp,
                        rule_results=rule_results,
                        blocking_rule=res.rule.value,
                        reason=res.detail,
                    )

            # All rules passed
            token = self._generate_verdict_token(
                order.order_id, order.portfolio_id, RiskDecision.passed, snapshot.timestamp
            )
            return RiskVerdict(
                decision=RiskDecision.passed,
                verdict_token=token,
                order_id=order.order_id,
                portfolio_id=order.portfolio_id,
                timestamp=snapshot.timestamp,
                rule_results=rule_results,
                blocking_rule=None,
                reason="All risk rules passed.",
            )

        except Exception as exc:
            # FAIL-CLOSED: Any evaluation failure must block the order immediately
            log.exception(f"Risk evaluation pipeline error for order {order.order_id}: {exc}")
            fail_closed_result = RuleEvaluationResult(
                rule="pipeline_fail_closed",
                decision=RiskDecision.blocked,
                observed_value="exception",
                threshold_value="normal_execution",
                detail=f"Fail-closed safe block due to evaluation error: {str(exc)}",
            )
            rule_results.append(fail_closed_result)
            token = self._generate_verdict_token(
                order.order_id, order.portfolio_id, RiskDecision.blocked, snapshot.timestamp
            )
            return RiskVerdict(
                decision=RiskDecision.blocked,
                verdict_token=token,
                order_id=order.order_id,
                portfolio_id=order.portfolio_id,
                timestamp=snapshot.timestamp,
                rule_results=rule_results,
                blocking_rule="pipeline_fail_closed",
                reason=f"Pipeline exception (fail-closed): {str(exc)}",
            )
