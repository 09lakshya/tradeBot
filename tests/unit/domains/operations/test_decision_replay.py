"""Unit tests for Decision Replay Engine."""
from __future__ import annotations

from app.domains.operations.decision_replay import DecisionReplayEngine


def test_decision_replay_controls():
    engine = DecisionReplayEngine()
    session = engine.create_replay_session(date="2026-08-04", synthetic_steps_count=5)

    assert session.total_steps == 5
    assert session.current_step == 0

    engine.play(session.session_id)
    retrieved = engine.get_session(session.session_id)
    assert retrieved.is_playing is True

    engine.pause(session.session_id)
    assert engine.get_session(session.session_id).is_playing is False

    step1 = engine.step_forward(session.session_id)
    assert step1.step_number == 1

    step0 = engine.step_backward(session.session_id)
    assert step0.step_number == 0

    seeked = engine.seek(session.session_id, 4)
    assert seeked.step_number == 4
