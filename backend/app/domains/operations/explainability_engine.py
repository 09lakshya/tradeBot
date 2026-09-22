"""Strategy Explainability Engine for Phase 10."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.domains.operations.models import (
    ExecutionReason,
    PortfolioReason,
    RiskReason,
    SignalReason,
    TradeExplanation,
)
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.explainability")
DEFAULT_EXPLANATION_DIR = Path("scratch/trade_explanations")


class StrategyExplainabilityEngine:
    """Captures granular trade decision lineage and generates human-readable narrative explanations."""

    def __init__(self, storage_dir: Path = DEFAULT_EXPLANATION_DIR) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._explanations: dict[str, TradeExplanation] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def record_explanation(
        self,
        trade_id: str,
        strategy_id: str,
        symbol: str,
        side: str,
        signal_reason: SignalReason,
        risk_reason: RiskReason,
        portfolio_reason: PortfolioReason,
        execution_reason: ExecutionReason,
        order_id: str | None = None,
        exit_reason: str | None = None,
    ) -> TradeExplanation:
        """Constructs narrative explanation and records decision lineage."""
        narrative = self.generate_narrative(
            symbol=symbol,
            side=side,
            signal_reason=signal_reason,
            risk_reason=risk_reason,
            portfolio_reason=portfolio_reason,
            execution_reason=execution_reason,
            exit_reason=exit_reason,
        )

        explanation = TradeExplanation(
            trade_id=trade_id,
            order_id=order_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            signal_reason=signal_reason,
            risk_reason=risk_reason,
            portfolio_reason=portfolio_reason,
            execution_reason=execution_reason,
            exit_reason=exit_reason,
            narrative=narrative,
        )

        with self._lock:
            self._explanations[trade_id] = explanation
            self._persist_explanation(explanation)
            logger.info("trade_explanation_recorded", trade_id=trade_id, strategy_id=strategy_id)

        return explanation

    def generate_narrative(
        self,
        symbol: str,
        side: str,
        signal_reason: SignalReason,
        risk_reason: RiskReason,
        portfolio_reason: PortfolioReason,
        execution_reason: ExecutionReason,
        exit_reason: str | None = None,
    ) -> str:
        """Generates clear narrative text for institutional trade explanations."""
        ind_str = ", ".join([f"{k}={v}" for k, v in signal_reason.indicator_values.items()])
        narrative_parts = [
            f"Signal generated for {side} {symbol} with confidence {signal_reason.confidence_score:.0%}. "
            f"Key indicators ({ind_str}): {signal_reason.rationale}.",
            f"Portfolio accepted allocation of {portfolio_reason.allocation_weight:.1%} capital "
            f"(size: ₹{portfolio_reason.position_sizing_selected:,.2f}) based on {portfolio_reason.sizing_rationale}.",
            f"Risk engine approved trade execution: {risk_reason.rationale}.",
            f"Execution executed at ₹{execution_reason.fill_price:,.2f} with slippage {execution_reason.slippage:.4f} and commission ₹{execution_reason.commission:.2f}.",
        ]

        if exit_reason:
            narrative_parts.append(f"Trade exited due to: {exit_reason}.")

        return " ".join(narrative_parts)

    def get_explanation(self, trade_id: str) -> TradeExplanation | None:
        with self._lock:
            return self._explanations.get(trade_id)

    def list_explanations(
        self,
        strategy_id: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[TradeExplanation]:
        with self._lock:
            res = list(self._explanations.values())
            if strategy_id:
                res = [e for e in res if e.strategy_id == strategy_id]
            if symbol:
                res = [e for e in res if e.symbol == symbol]
            return res[-limit:]

    def _persist_explanation(self, explanation: TradeExplanation) -> None:
        filepath = self.storage_dir / f"explanation_{explanation.trade_id}.json"
        filepath.write_text(explanation.model_dump_json(indent=2), encoding="utf-8")

    def _load_persisted(self) -> None:
        for file in self.storage_dir.glob("explanation_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                explanation = TradeExplanation(**data)
                self._explanations[explanation.trade_id] = explanation
            except Exception as exc:
                logger.warning("explanation_load_failed", file=str(file), error=str(exc))
