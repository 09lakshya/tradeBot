"""Indian Equity Market (NSE/BSE) Session Manager with holiday calendars and session transitions."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domains.orchestrator.enums import SessionState
from app.domains.orchestrator.exceptions import HolidaySessionError, MarketClosedError
from app.domains.orchestrator.schemas import SessionStatusResponse

# Indian Standard Time (UTC+05:30)
IST_TZ = ZoneInfo("Asia/Kolkata")

# Standard Indian Trading Session Windows (IST)
TIME_PRE_OPEN_START = time(9, 0, 0)
TIME_PRE_OPEN_MATCH_START = time(9, 8, 0)
TIME_REGULAR_START = time(9, 15, 0)
TIME_REGULAR_END = time(15, 30, 0)
TIME_CLOSING_AUCTION_END = time(15, 40, 0)
TIME_POST_MARKET_END = time(16, 0, 0)

# Standard NSE/BSE Annual Holidays (YYYY-MM-DD -> Holiday Name)
DEFAULT_INDIAN_HOLIDAYS: dict[str, str] = {
    # 2024 Holidays
    "2024-01-22": "Special Holiday (Ayodhya Ram Mandir)",
    "2024-01-26": "Republic Day",
    "2024-03-08": "Mahashivratri",
    "2024-03-25": "Holi",
    "2024-03-29": "Good Friday",
    "2024-04-11": "Id-Ul-Fitr (Ramzan Id)",
    "2024-04-17": "Ram Navami",
    "2024-05-01": "Maharashtra Day",
    "2024-05-20": "General Parliamentary Elections (Mumbai)",
    "2024-06-17": "Bakri Id / Eid-ul-Adha",
    "2024-07-17": "Muharram",
    "2024-08-15": "Independence Day",
    "2024-10-02": "Mahatma Gandhi Jayanti",
    "2024-11-01": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2024-11-15": "Gurunanak Jayanti",
    "2024-11-20": "Maharashtra Assembly Elections",
    "2024-12-25": "Christmas",
    # 2025 Holidays
    "2025-01-26": "Republic Day",
    "2025-02-26": "Mahashivratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-Ul-Fitr",
    "2025-04-10": "Mahavir Jayanti",
    "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-08-15": "Independence Day",
    "2025-08-27": "Ganesh Chaturthi",
    "2025-10-02": "Mahatma Gandhi Jayanti / Dussehra",
    "2025-10-21": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2025-10-22": "Diwali Balipratipada",
    "2025-11-05": "Gurunanak Jayanti",
    "2025-12-25": "Christmas",
    # 2026 Holidays
    "2026-01-26": "Republic Day",
    "2026-03-04": "Holi",
    "2026-03-20": "Id-Ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-08-15": "Independence Day",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2026-11-24": "Gurunanak Jayanti",
    "2026-12-25": "Christmas",
}

# Special Muhurat Trading Session Schedules (YYYY-MM-DD -> (start_time, end_time))
DEFAULT_MUHURAT_SESSIONS: dict[str, tuple[time, time]] = {
    "2024-11-01": (time(18, 0, 0), time(19, 0, 0)),
    "2025-10-21": (time(18, 15, 0), time(19, 15, 0)),
    "2026-11-08": (time(18, 0, 0), time(19, 0, 0)),
}


class MarketSessionManager:
    """Manages Indian Market (NSE/BSE) trading hours, session states, and holiday calendars."""

    def __init__(
        self,
        holidays: dict[str, str] | None = None,
        muhurat_sessions: dict[str, tuple[time, time]] | None = None,
        exchange: str = "NSE",
    ):
        self.holidays = holidays if holidays is not None else DEFAULT_INDIAN_HOLIDAYS
        self.muhurat_sessions = muhurat_sessions if muhurat_sessions is not None else DEFAULT_MUHURAT_SESSIONS
        self.exchange = exchange

    def to_ist(self, dt: datetime) -> datetime:
        """Converts any datetime (UTC or naive) to Indian Standard Time (IST)."""
        if dt.tzinfo is None:
            # Treat naive datetime as UTC by default
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST_TZ)

    def is_weekend(self, dt_ist: datetime) -> bool:
        """Returns True if the given IST datetime falls on Saturday (5) or Sunday (6)."""
        return dt_ist.weekday() in (5, 6)

    def is_holiday(self, dt_ist: datetime) -> tuple[bool, str | None]:
        """Checks if the date is an exchange holiday. Returns (is_holiday, holiday_name)."""
        date_key = dt_ist.strftime("%Y-%m-%d")
        if date_key in self.holidays:
            return True, self.holidays[date_key]
        return False, None

    def get_session_state(self, dt: datetime) -> SessionState:
        """Determines the exact market session state for a given timestamp."""
        dt_ist = self.to_ist(dt)
        date_key = dt_ist.strftime("%Y-%m-%d")
        t = dt_ist.time()

        # Check for special Muhurat Trading session
        if date_key in self.muhurat_sessions:
            m_start, m_end = self.muhurat_sessions[date_key]
            if m_start <= t < m_end:
                return SessionState.regular_hours
            return SessionState.closed

        # Weekends are closed
        if self.is_weekend(dt_ist):
            return SessionState.closed

        # Exchange holidays are closed
        is_hol, _ = self.is_holiday(dt_ist)
        if is_hol:
            return SessionState.closed

        # Weekday standard session windows
        if t < TIME_PRE_OPEN_START:
            return SessionState.closed
        elif TIME_PRE_OPEN_START <= t < TIME_PRE_OPEN_MATCH_START:
            return SessionState.pre_open
        elif TIME_PRE_OPEN_MATCH_START <= t < TIME_REGULAR_START:
            return SessionState.pre_open_matching
        elif TIME_REGULAR_START <= t < TIME_REGULAR_END:
            return SessionState.regular_hours
        elif TIME_REGULAR_END <= t < TIME_CLOSING_AUCTION_END:
            return SessionState.closing_auction
        elif TIME_CLOSING_AUCTION_END <= t < TIME_POST_MARKET_END:
            return SessionState.post_market
        else:
            return SessionState.closed

    def is_market_open(self, dt: datetime) -> bool:
        """Returns True if continuous regular trading is currently active."""
        return self.get_session_state(dt) == SessionState.regular_hours

    def validate_can_trade(self, dt: datetime, enforce: bool = True) -> None:
        """Raises an exception if execution is attempted outside regular trading hours."""
        if not enforce:
            return

        dt_ist = self.to_ist(dt)
        is_hol, holiday_name = self.is_holiday(dt_ist)
        if is_hol and dt_ist.strftime("%Y-%m-%d") not in self.muhurat_sessions:
            raise HolidaySessionError(holiday_name or "Exchange Holiday", dt_ist.strftime("%Y-%m-%d"))

        state = self.get_session_state(dt)
        if state != SessionState.regular_hours:
            raise MarketClosedError(
                f"Trading rejected: {self.exchange} session state is '{state.value}' at {dt_ist.strftime('%Y-%m-%d %H:%M:%S IST')}."
            )

    def get_session_status(self, dt: datetime) -> SessionStatusResponse:
        """Builds a comprehensive session diagnostic response."""
        dt_ist = self.to_ist(dt)
        state = self.get_session_state(dt)
        is_hol, hol_name = self.is_holiday(dt_ist)

        # Calculate next transition
        next_trans = self._calculate_next_transition(dt_ist, state)

        return SessionStatusResponse(
            exchange=self.exchange,
            session_state=state,
            is_market_open=state == SessionState.regular_hours,
            is_holiday=is_hol,
            is_half_day=False,
            current_time_ist=dt_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
            next_transition_time=next_trans.strftime("%Y-%m-%d %H:%M:%S IST") if next_trans else None,
            holiday_name=hol_name,
        )

    def _calculate_next_transition(self, dt_ist: datetime, state: SessionState) -> datetime | None:
        """Calculates the upcoming session transition timestamp."""
        today = dt_ist.date()
        if state == SessionState.pre_open:
            return datetime.combine(today, TIME_PRE_OPEN_MATCH_START, tzinfo=IST_TZ)
        elif state == SessionState.pre_open_matching:
            return datetime.combine(today, TIME_REGULAR_START, tzinfo=IST_TZ)
        elif state == SessionState.regular_hours:
            return datetime.combine(today, TIME_REGULAR_END, tzinfo=IST_TZ)
        elif state == SessionState.closing_auction:
            return datetime.combine(today, TIME_CLOSING_AUCTION_END, tzinfo=IST_TZ)
        elif state == SessionState.post_market:
            return datetime.combine(today, TIME_POST_MARKET_END, tzinfo=IST_TZ)
        else:
            # Closed: next transition is 09:00 IST on next trading day
            next_day = today + timedelta(days=1)
            while True:
                candidate = datetime.combine(next_day, TIME_PRE_OPEN_START, tzinfo=IST_TZ)
                if not self.is_weekend(candidate):
                    is_h, _ = self.is_holiday(candidate)
                    if not is_h:
                        return candidate
                next_day += timedelta(days=1)
                if (next_day - today).days > 10:
                    return None
