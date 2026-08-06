"""Position Sizing Engine with transaction cost awareness and mathematical explainability."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import math
from typing import Any
import uuid

from app.domains.portfolio.enums import CandidateOrderStatus, SizingMethod
from app.domains.portfolio.exceptions import SizingError
from app.domains.portfolio.schemas import (
    ArbitrationDecision,
    CandidateOrder,
    PortfolioConstructionConfig,
    PortfolioSnapshot,
    SignalRankingScore,
    TransactionCostEstimate,
)
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.cost_engine import CostEngine
from app.domains.trading.enums import OrderSide, ProductType


class PositionSizingEngine:
    """Calculates discrete share quantities, estimates transaction costs, and constructs immutable CandidateOrders."""

    def __init__(self, cost_engine: CostEngine | None = None):
        self.cost_engine = cost_engine or CostEngine()

    def size_positions(
        self,
        plan_id: uuid.UUID,
        decisions: dict[uuid.UUID, ArbitrationDecision],
        target_weights: dict[uuid.UUID, Decimal],
        snapshot: PortfolioSnapshot,
        signals_map: dict[uuid.UUID, list[TradingSignal]],
        ranking_scores: dict[uuid.UUID, SignalRankingScore],
        config: PortfolioConstructionConfig,
        current_prices: dict[uuid.UUID, Decimal] | None = None,
        optimization_explanations: dict[str, str] | None = None,
    ) -> list[CandidateOrder]:
        """Translates target weights into immutable CandidateOrders with full decision attribution."""
        candidate_orders: list[CandidateOrder] = []
        prices = current_prices or {}
        opt_expl = optimization_explanations or {}

        for inst_id, target_w in target_weights.items():
            if inst_id not in decisions:
                continue

            decision = decisions[inst_id]
            if decision.winning_side is None:
                continue

            # Determine price for sizing
            price = prices.get(inst_id) or decision.blended_entry_price
            if not price or price <= 0:
                # Fallback to existing position market price if available
                if inst_id in snapshot.positions:
                    price = snapshot.positions[inst_id].current_market_price
                else:
                    price = Decimal("100.0000")  # Default conservative unit estimate

            # Calculate Quantity based on SizingMethod
            qty, sizing_meta = self._calculate_quantity(
                inst_id=inst_id,
                target_w=target_w,
                price=price,
                snapshot=snapshot,
                decision=decision,
                config=config,
            )

            if qty <= 0:
                continue

            estimated_notional = (qty * price).quantize(Decimal("0.0001"))

            # Estimate Transaction Costs
            costs = self._estimate_transaction_costs(
                symbol=decision.symbol,
                side=decision.winning_side,
                quantity=qty,
                price=price,
            )

            # Extract source signals & strategies
            inst_signals = signals_map.get(inst_id, [])
            selected_sigs = [s for s in inst_signals if s.signal_id in decision.selected_signals]
            strategy_sources = list(set(s.strategy_id for s in selected_sigs))
            signal_sources = [s.signal_id for s in selected_sigs]

            # Aggregate ranking score & breakdown
            sig_scores = [
                ranking_scores[s.signal_id].composite_score
                for s in selected_sigs
                if s.signal_id in ranking_scores
            ]
            avg_rank_score = sum(sig_scores) / len(sig_scores) if sig_scores else 0.5

            first_sig = selected_sigs[0] if selected_sigs else None
            scoring_breakdown = (
                ranking_scores[first_sig.signal_id].feature_breakdown
                if first_sig and first_sig.signal_id in ranking_scores
                else {}
            )

            # Build reasoning text
            reason = (
                f"Candidate {decision.winning_side.value.upper()} {qty} shares of {decision.symbol} "
                f"at est. price {price:.2f} (Notional: {estimated_notional:.2f}, Weight: {target_w * 100:.2f}%). "
                f"Sizing: {config.sizing_method.value}. Arbitration: {decision.reason}. "
                f"Opt Reason: {opt_expl.get(str(inst_id), 'Optimized allocation')}."
            )

            # Build explainability ancestry trace
            explainability_trace = {
                "plan_id": str(plan_id),
                "instrument_id": str(inst_id),
                "symbol": decision.symbol,
                "allocation_policy": config.allocation_policy.value,
                "sizing_method": config.sizing_method.value,
                "target_weight": float(target_w),
                "current_weight": float(snapshot.current_weights.get(inst_id, Decimal("0.0000"))),
                "arbitration": {
                    "conflict_type": decision.conflict_type,
                    "resolution_method": decision.resolution_method.value,
                    "selected_signals": [str(sid) for sid in decision.selected_signals],
                    "discarded_signals": [str(sid) for sid in decision.discarded_signals],
                },
                "ranking_breakdown": scoring_breakdown,
                "sizing_breakdown": sizing_meta,
                "transaction_costs_summary": {
                    "total_frictional_costs": float(costs.total_estimated_costs),
                    "slippage": float(costs.estimated_slippage),
                },
            }

            candidate = CandidateOrder(
                plan_id=plan_id,
                portfolio_id=snapshot.portfolio_id,
                instrument_id=inst_id,
                symbol=decision.symbol,
                side=decision.winning_side,
                product_type=ProductType.cnc,
                quantity=qty,
                target_weight=target_w,
                current_weight=snapshot.current_weights.get(inst_id, Decimal("0.0000")),
                estimated_price=price,
                estimated_notional=estimated_notional,
                stop_loss=decision.blended_stop_loss,
                take_profit=decision.blended_take_profit,
                confidence=decision.blended_confidence,
                expected_return=getattr(first_sig, "expected_return", None) if first_sig else None,
                expected_risk=getattr(first_sig, "expected_risk", None) if first_sig else None,
                risk_reward_ratio=getattr(first_sig, "risk_reward_ratio", None) if first_sig else None,
                strategy_sources=strategy_sources,
                signal_sources=signal_sources,
                ranking_score=avg_rank_score,
                ranking_breakdown=scoring_breakdown,
                sizing_method=config.sizing_method,
                sizing_breakdown=sizing_meta,
                transaction_costs=costs,
                reasoning=reason,
                explainability_trace=explainability_trace,
                status=CandidateOrderStatus.generated,
            )
            candidate_orders.append(candidate)

        return candidate_orders

    def _calculate_quantity(
        self,
        inst_id: uuid.UUID,
        target_w: Decimal,
        price: Decimal,
        snapshot: PortfolioSnapshot,
        decision: ArbitrationDecision,
        config: PortfolioConstructionConfig,
    ) -> tuple[Decimal, dict[str, Any]]:
        """Computes discrete share quantities and returns mathematical sizing metadata."""
        equity = snapshot.total_equity
        target_notional = equity * target_w

        if config.sizing_method == SizingMethod.fixed_fractional:
            raw_qty = (target_notional / price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            meta = {"formula": "fixed_fractional", "target_notional": float(target_notional)}
            return raw_qty, meta

        elif config.sizing_method == SizingMethod.volatility_adjusted:
            vol = snapshot.volatilities.get(inst_id, Decimal("0.2000"))
            vol_safe = max(Decimal("0.0100"), vol)
            # Inverse volatility scalar relative to benchmark 20% vol
            vol_scalar = min(Decimal("2.0"), Decimal("0.2000") / vol_safe)
            adjusted_notional = target_notional * vol_scalar
            raw_qty = (adjusted_notional / price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            meta = {
                "formula": "volatility_adjusted",
                "volatility": float(vol),
                "vol_scalar": float(vol_scalar),
                "adjusted_notional": float(adjusted_notional),
            }
            return raw_qty, meta

        elif config.sizing_method == SizingMethod.atr_risk_per_trade:
            # Sizing by Dollar Risk: Risk Amount = Equity * risk_per_trade_pct
            risk_budget = equity * config.risk_per_trade_pct
            # Estimate stop distance in price
            if decision.blended_stop_loss and decision.blended_stop_loss > 0:
                stop_dist = abs(price - decision.blended_stop_loss)
            else:
                stop_dist = price * Decimal("0.02")  # 2% default stop distance
            stop_dist = max(Decimal("0.01"), stop_dist)

            raw_qty = (risk_budget / stop_dist).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            # Bound by target_notional cap
            max_qty_by_weight = (target_notional / price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            bounded_qty = min(raw_qty, max_qty_by_weight)
            meta = {
                "formula": "atr_risk_per_trade",
                "risk_budget": float(risk_budget),
                "stop_distance": float(stop_dist),
                "unbounded_qty": float(raw_qty),
            }
            return bounded_qty, meta

        elif config.sizing_method in (SizingMethod.half_kelly, SizingMethod.full_kelly):
            # Kelly formula: f* = (p*b - (1-p)) / b
            # Assume win rate p=0.55, payoff ratio b=1.5 default
            p = 0.55
            b = 1.50
            f_star = (p * b - (1.0 - p)) / b
            damping = config.half_kelly_damping if config.sizing_method == SizingMethod.half_kelly else 1.0
            kelly_pct = Decimal(str(max(0.0, f_star * damping)))
            kelly_notional = equity * min(kelly_pct, target_w)
            raw_qty = (kelly_notional / price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            meta = {
                "formula": config.sizing_method.value,
                "f_star": f_star,
                "kelly_pct": float(kelly_pct),
                "kelly_notional": float(kelly_notional),
            }
            return raw_qty, meta

        else:
            raw_qty = (target_notional / price).quantize(Decimal("1"), rounding=ROUND_FLOOR)
            return raw_qty, {"formula": "default_fractional"}

    def _estimate_transaction_costs(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
    ) -> TransactionCostEstimate:
        """Calculates expected execution and statutory frictional costs for Indian equity markets."""
        trade_value = quantity * price

        # Brokerage: 0.03% or Rs 20 (whichever is lower for equity delivery/intraday)
        brokerage = min(Decimal("20.00"), trade_value * Decimal("0.0003")).quantize(Decimal("0.0001"))
        
        # STT: 0.1% on delivery buy/sell
        stt = (trade_value * Decimal("0.0010")).quantize(Decimal("0.0001"))

        # Exchange turnover: 0.00345%
        exch_turnover = (trade_value * Decimal("0.0000345")).quantize(Decimal("0.0001"))

        # GST: 18% on (Brokerage + Exchange)
        gst = ((brokerage + exch_turnover) * Decimal("0.1800")).quantize(Decimal("0.0001"))

        # SEBI charges: 0.0001%
        sebi = (trade_value * Decimal("0.000001")).quantize(Decimal("0.0001"))

        # Stamp duty: 0.015% on BUY
        stamp = (trade_value * Decimal("0.00015")).quantize(Decimal("0.0001")) if side == OrderSide.buy else Decimal("0.0000")

        # Slippage: 5 bps (0.05%)
        slippage = (trade_value * Decimal("0.0005")).quantize(Decimal("0.0001"))

        total = brokerage + stt + exch_turnover + gst + sebi + stamp + slippage

        return TransactionCostEstimate(
            estimated_brokerage=brokerage,
            estimated_stt=stt,
            estimated_exchange_turnover=exch_turnover,
            estimated_gst=gst,
            estimated_sebi_charges=sebi,
            estimated_stamp_duty=stamp,
            estimated_slippage=slippage,
            total_estimated_costs=total,
        )
