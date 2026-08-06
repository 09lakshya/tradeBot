"""Decision Replay Engine for Phase 10."""
from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any

from app.domains.operations.models import ReplaySessionState, ReplayStep
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.replay")


class DecisionReplayEngine:
    """Historical trading day step-by-step decision replay engine."""

    def __init__(self) -> None:
        self._sessions: dict[str, ReplaySessionState] = {}
        self._lock = threading.Lock()

    def create_replay_session(
        self,
        date: str,
        synthetic_steps_count: int = 10,
    ) -> ReplaySessionState:
        """Initializes a historical decision replay session for a specific trading day."""
        steps: list[ReplayStep] = []
        base_pv = 100000.0

        for i in range(synthetic_steps_count):
            step_pv = base_pv + (i * 150.0)
            step = ReplayStep(
                step_number=i,
                timestamp=f"{date}T09:{30+i:02d}:00Z",
                market_prices={"RELIANCE.NS": 2950.0 + (i * 2.5), "TCS.NS": 4120.0 - (i * 1.2)},
                signals_generated=[
                    {
                        "strategy_id": "trend_following_v1",
                        "symbol": "RELIANCE.NS",
                        "signal": "BUY" if i % 3 == 0 else "HOLD",
                        "confidence": 0.85,
                    }
                ],
                portfolio_decisions=[
                    {
                        "symbol": "RELIANCE.NS",
                        "target_qty": 50 if i % 3 == 0 else 0,
                        "weight": 0.09,
                    }
                ],
                risk_evaluations=[
                    {
                        "rule": "max_drawdown",
                        "status": "PASSED",
                        "limit": 0.05,
                        "current": 0.01,
                    }
                ],
                orders_issued=(
                    [{"order_id": f"ord_{i}", "symbol": "RELIANCE.NS", "side": "BUY", "qty": 50}]
                    if i % 3 == 0
                    else []
                ),
                positions_state=[{"symbol": "RELIANCE.NS", "qty": 50 * (i // 3 + 1), "pnl": i * 25.0}],
                portfolio_value=step_pv,
                cash_balance=step_pv - 9000.0,
            )
            steps.append(step)

        session = ReplaySessionState(
            date=date,
            current_step=0,
            total_steps=len(steps),
            is_playing=False,
            speed_multiplier=1.0,
            steps=steps,
        )

        with self._lock:
            self._sessions[session.session_id] = session
            logger.info("replay_session_created", session_id=session.session_id, date=date, steps=len(steps))

        return session

    def get_session(self, session_id: str) -> ReplaySessionState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def play(self, session_id: str, speed_multiplier: float = 1.0) -> ReplaySessionState:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Replay session {session_id} not found")
            session.is_playing = True
            session.speed_multiplier = speed_multiplier
            return session

    def pause(self, session_id: str) -> ReplaySessionState:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Replay session {session_id} not found")
            session.is_playing = False
            return session

    def step_forward(self, session_id: str) -> ReplayStep | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Replay session {session_id} not found")
            if session.current_step < session.total_steps - 1:
                session.current_step += 1
            return session.steps[session.current_step] if session.steps else None

    def step_backward(self, session_id: str) -> ReplayStep | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Replay session {session_id} not found")
            if session.current_step > 0:
                session.current_step -= 1
            return session.steps[session.current_step] if session.steps else None

    def seek(self, session_id: str, target_step: int) -> ReplayStep | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Replay session {session_id} not found")
            bounded_step = max(0, min(target_step, session.total_steps - 1))
            session.current_step = bounded_step
            return session.steps[bounded_step] if session.steps else None
