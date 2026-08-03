"""Exchange session primitives with no dependencies beyond the enums.

Timezone lookup lives here rather than in ``calendar.py`` so provider adapters
can resolve an exchange's local time without pulling in the database-backed
calendar service.
"""
from zoneinfo import ZoneInfo

from app.domains.market_data.enums import Exchange

IST = ZoneInfo("Asia/Kolkata")

#: Local timezone per exchange. Date-bounded queries and session alignment must be
#: evaluated in exchange-local time, never UTC — an IST trading day starts at
#: 18:30 UTC on the *previous* calendar date, so a UTC-framed window silently
#: drops the first day's bars. Future exchanges add an entry here and nothing else.
EXCHANGE_TIMEZONES: dict[Exchange, ZoneInfo] = {
    Exchange.NSE: IST,
    Exchange.BSE: IST,
}


def exchange_timezone(exchange: Exchange) -> ZoneInfo:
    return EXCHANGE_TIMEZONES.get(exchange, IST)
