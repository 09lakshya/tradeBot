"""Unit tests for SignalAggregator."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest

from app.domains.portfolio.aggregator import SignalAggregator
from app.domains.portfolio.exceptions import IncompatibleSignalError
from app.domains.portfolio.schemas import PortfolioSnapshot
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal


def create_signal(
    instrument_id: uuid.UUID,
    symbol: str,
    timestamp: datetime,
    strategy_id: str = "trend_strategy",
    confidence: float = 0.85,
    expiry: datetime | None = None,
) -> TradingSignal:
    return TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        symbol=symbol,
        timestamp=timestamp,
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=confidence,
        signal_expiry=expiry,
    )


def test_aggregator_groups_by_instrument():
    aggregator = SignalAggregator(default_ttl_seconds=3600)
    inst_1 = uuid.uuid4()
    inst_2 = uuid.uuid4()
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

    sig1 = create_signal(inst_1, "TCS", now - timedelta(minutes=5), "strat_a")
    sig2 = create_signal(inst_1, "TCS", now - timedelta(minutes=2), "strat_b")
    sig3 = create_signal(inst_2, "INFY", now - timedelta(minutes=1), "strat_a")

    grouped = aggregator.aggregate([sig1, sig2, sig3], current_time=now)
    assert len(grouped) == 2
    assert len(grouped[inst_1]) == 2
    assert len(grouped[inst_2]) == 1


def test_aggregator_discards_expired_signals():
    aggregator = SignalAggregator(default_ttl_seconds=1800)  # 30 min TTL
    inst_1 = uuid.uuid4()
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

    # 45 minutes old (exceeds default TTL)
    sig_old = create_signal(inst_1, "TCS", now - timedelta(minutes=45))
    # 10 minutes old
    sig_fresh = create_signal(inst_1, "TCS", now - timedelta(minutes=10))
    # Explicit expiry in the past
    sig_expired = create_signal(
        inst_1, "TCS", now - timedelta(minutes=5), expiry=now - timedelta(minutes=1)
    )

    grouped = aggregator.aggregate([sig_old, sig_fresh, sig_expired], current_time=now)
    assert len(grouped[inst_1]) == 1
    assert grouped[inst_1][0].signal_id == sig_fresh.signal_id


def test_aggregator_rejects_lookahead_future_signals():
    aggregator = SignalAggregator()
    inst_1 = uuid.uuid4()
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

    # Future timestamp (10:15 > 10:00)
    sig_future = create_signal(inst_1, "TCS", now + timedelta(minutes=15))

    with pytest.raises(IncompatibleSignalError, match="Look-ahead signal detected"):
        aggregator.aggregate([sig_future], current_time=now)


def test_aggregator_applies_min_daily_volume_filter():
    aggregator = SignalAggregator()
    inst_liquid = uuid.uuid4()
    inst_illiquid = uuid.uuid4()
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

    snapshot = PortfolioSnapshot(
        portfolio_id=uuid.uuid4(),
        timestamp=now,
        cash_balance=Decimal("100000.00"),
        total_equity=Decimal("100000.00"),
        historical_volumes={
            inst_liquid: Decimal("50000"),
            inst_illiquid: Decimal("2000"),
        },
    )

    sig_liq = create_signal(inst_liquid, "RELIANCE", now - timedelta(minutes=1))
    sig_illiq = create_signal(inst_illiquid, "PENNY_STOCK", now - timedelta(minutes=1))

    grouped = aggregator.aggregate(
        [sig_liq, sig_illiq],
        current_time=now,
        portfolio_snapshot=snapshot,
        min_daily_volume=Decimal("10000"),
    )

    assert inst_liquid in grouped
    assert inst_illiquid not in grouped
