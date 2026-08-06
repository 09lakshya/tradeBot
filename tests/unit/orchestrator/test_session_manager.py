"""Unit tests for the Indian Market (NSE/BSE) Session Manager."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import pytest

from app.domains.orchestrator.enums import SessionState
from app.domains.orchestrator.exceptions import HolidaySessionError, MarketClosedError
from app.domains.orchestrator.session_manager import IST_TZ, MarketSessionManager


def test_session_manager_ist_conversion():
    mgr = MarketSessionManager()
    # 03:45 UTC is 09:15 IST (Market Open)
    utc_dt = datetime(2025, 4, 15, 3, 45, 0, tzinfo=timezone.utc)
    ist_dt = mgr.to_ist(utc_dt)
    assert ist_dt.hour == 9
    assert ist_dt.minute == 15
    assert ist_dt.tzinfo == IST_TZ


def test_session_states_regular_weekday():
    mgr = MarketSessionManager()
    # 2025-04-15 is a Tuesday (Trading Day)
    
    # 08:30 IST -> Closed
    dt_closed = datetime(2025, 4, 15, 8, 30, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_closed) == SessionState.closed
    assert not mgr.is_market_open(dt_closed)

    # 09:05 IST -> Pre-Open
    dt_pre = datetime(2025, 4, 15, 9, 5, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_pre) == SessionState.pre_open
    assert not mgr.is_market_open(dt_pre)

    # 09:10 IST -> Pre-Open Matching
    dt_match = datetime(2025, 4, 15, 9, 10, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_match) == SessionState.pre_open_matching

    # 10:30 IST -> Regular Hours (Open)
    dt_reg = datetime(2025, 4, 15, 10, 30, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_reg) == SessionState.regular_hours
    assert mgr.is_market_open(dt_reg)

    # 15:35 IST -> Closing Auction
    dt_close = datetime(2025, 4, 15, 15, 35, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_close) == SessionState.closing_auction

    # 15:50 IST -> Post-Market
    dt_post = datetime(2025, 4, 15, 15, 50, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_post) == SessionState.post_market

    # 16:30 IST -> Closed
    dt_after = datetime(2025, 4, 15, 16, 30, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_after) == SessionState.closed


def test_weekend_handling():
    mgr = MarketSessionManager()
    # 2025-04-19 is a Saturday
    dt_sat = datetime(2025, 4, 19, 11, 0, 0, tzinfo=IST_TZ)
    assert mgr.is_weekend(dt_sat)
    assert mgr.get_session_state(dt_sat) == SessionState.closed
    assert not mgr.is_market_open(dt_sat)


def test_holiday_handling():
    mgr = MarketSessionManager()
    # 2025-08-15 is Independence Day (Friday)
    dt_hol = datetime(2025, 8, 15, 11, 0, 0, tzinfo=IST_TZ)
    is_hol, hol_name = mgr.is_holiday(dt_hol)
    assert is_hol is True
    assert "Independence" in hol_name
    assert mgr.get_session_state(dt_hol) == SessionState.closed

    with pytest.raises(HolidaySessionError):
        mgr.validate_can_trade(dt_hol, enforce=True)


def test_muhurat_trading_session():
    mgr = MarketSessionManager(
        muhurat_sessions={"2025-10-21": (time(18, 15, 0), time(19, 15, 0))}
    )
    # Outside Muhurat window on Diwali -> Closed
    dt_before = datetime(2025, 10, 21, 14, 0, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_before) == SessionState.closed

    # Inside Muhurat window (18:30 IST) -> Regular Hours
    dt_muhurat = datetime(2025, 10, 21, 18, 30, 0, tzinfo=IST_TZ)
    assert mgr.get_session_state(dt_muhurat) == SessionState.regular_hours
    assert mgr.is_market_open(dt_muhurat)
    mgr.validate_can_trade(dt_muhurat, enforce=True)  # Should not raise


def test_session_status_response():
    mgr = MarketSessionManager()
    dt_reg = datetime(2025, 4, 15, 10, 0, 0, tzinfo=IST_TZ)
    resp = mgr.get_session_status(dt_reg)
    assert resp.exchange == "NSE"
    assert resp.session_state == SessionState.regular_hours
    assert resp.is_market_open is True
    assert resp.next_transition_time is not None
