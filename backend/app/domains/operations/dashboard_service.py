"""Portfolio Replay Dashboard Data Generator for Phase 10."""
from __future__ import annotations

from typing import Any

from app.domains.operations.schemas import DashboardReplayResponse


class DashboardService:
    """Generates structured widget payload data for the Portfolio Replay Dashboard."""

    def get_dashboard_data(self, days: int = 30) -> DashboardReplayResponse:
        """Generates portfolio replay dashboard data."""
        equity_curve: list[dict[str, Any]] = []
        capital_deployment: list[dict[str, Any]] = []
        trade_sequence: list[dict[str, Any]] = []
        position_history: list[dict[str, Any]] = []
        cash_movement: list[dict[str, Any]] = []
        risk_evolution: list[dict[str, Any]] = []
        cost_accumulation: list[dict[str, Any]] = []
        gross_vs_net_equity: list[dict[str, Any]] = []

        base_val = 100000.0
        cum_cost = 0.0

        for day in range(1, days + 1):
            date_str = f"2026-07-{day:02d}"
            gross = base_val + (day * 320.0)
            cum_cost += 15.0 + (day * 0.5)
            net = gross - cum_cost
            cash = 100000.0 - (day * 2000.0)
            invested = gross - cash

            equity_curve.append({"date": date_str, "equity": round(net, 2)})
            capital_deployment.append({"date": date_str, "cash": round(cash, 2), "invested": round(invested, 2)})
            cash_movement.append({"date": date_str, "cash": round(cash, 2), "delta": -2000.0})
            risk_evolution.append({"date": date_str, "var_95": round(1200 + (day * 10), 2), "leverage": round(invested / gross, 3)})
            cost_accumulation.append({"date": date_str, "cumulative_costs": round(cum_cost, 2)})
            gross_vs_net_equity.append({"date": date_str, "gross_equity": round(gross, 2), "net_equity": round(net, 2)})

            if day % 2 == 0:
                trade_sequence.append({
                    "trade_id": f"trd_{day}",
                    "date": date_str,
                    "symbol": "RELIANCE.NS" if day % 4 == 0 else "TCS.NS",
                    "side": "BUY",
                    "qty": 50,
                    "price": 2950.0 + (day * 10),
                    "pnl": 150.0 + (day * 10),
                })
                position_history.append({
                    "date": date_str,
                    "symbol": "RELIANCE.NS",
                    "position_size": 50 * (day // 2),
                    "unrealized_pnl": 350.0 + (day * 5),
                })

        return DashboardReplayResponse(
            equity_curve=equity_curve,
            capital_deployment=capital_deployment,
            trade_sequence=trade_sequence,
            position_history=position_history,
            cash_movement=cash_movement,
            risk_evolution=risk_evolution,
            cost_accumulation=cost_accumulation,
            gross_vs_net_equity=gross_vs_net_equity,
        )
