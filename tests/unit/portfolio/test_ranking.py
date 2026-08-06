"""Unit tests for SignalRankingEngine."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.enums import RankingMethod
from app.domains.portfolio.ranking import SignalRankingEngine
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal


def create_signal(
    symbol: str,
    confidence: float,
    rr: Decimal | None = None,
    age_minutes: int = 0,
    strategy_id: str = "strat_a",
    now: datetime = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
) -> TradingSignal:
    return TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id=strategy_id,
        instrument_id=uuid.uuid4(),
        symbol=symbol,
        timestamp=now - timedelta(minutes=age_minutes),
        signal_type=SignalType.entry_long,
        direction=SignalDirection.long,
        confidence=confidence,
        risk_reward_ratio=rr,
    )


def test_ranking_multi_factor_scoring():
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    engine = SignalRankingEngine(
        method=RankingMethod.multi_factor_linear,
        weights={"confidence": 0.40, "risk_reward": 0.30, "freshness": 0.30},
    )

    sig_high_quality = create_signal("AAA", confidence=0.95, rr=Decimal("3.0"), age_minutes=1, now=now)
    sig_low_quality = create_signal("BBB", confidence=0.40, rr=Decimal("1.0"), age_minutes=30, now=now)

    ranked = engine.rank_signals([sig_low_quality, sig_high_quality], current_time=now)
    assert len(ranked) == 2
    assert ranked[0].symbol == "AAA"
    assert ranked[0].rank == 1
    assert ranked[0].composite_score > ranked[1].composite_score
    assert "Rank 1" in ranked[0].explanation


def test_ranking_confidence_weighted_method():
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    engine = SignalRankingEngine(method=RankingMethod.confidence_weighted)

    sig1 = create_signal("AAA", confidence=0.70, now=now)
    sig2 = create_signal("BBB", confidence=0.90, now=now)

    ranked = engine.rank_signals([sig1, sig2], current_time=now)
    assert ranked[0].symbol == "BBB"
    assert ranked[0].composite_score == 0.90
    assert ranked[1].symbol == "AAA"
    assert ranked[1].composite_score == 0.70


def test_ranking_incorporates_strategy_sharpe():
    now = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    engine = SignalRankingEngine(
        method=RankingMethod.multi_factor_linear,
        weights={"historical_sharpe": 1.0},
    )

    sig_from_top_strat = create_signal("AAA", confidence=0.5, strategy_id="top_alpha", now=now)
    sig_from_avg_strat = create_signal("BBB", confidence=0.5, strategy_id="avg_alpha", now=now)

    sharpe_ratios = {"top_alpha": 2.7, "avg_alpha": 0.9}

    ranked = engine.rank_signals(
        [sig_from_avg_strat, sig_from_top_strat],
        current_time=now,
        strategy_sharpe_ratios=sharpe_ratios,
    )

    assert ranked[0].symbol == "AAA"
    assert ranked[0].feature_breakdown["historical_sharpe"] == 0.9  # 2.7 / 3.0
    assert ranked[1].feature_breakdown["historical_sharpe"] == 0.3  # 0.9 / 3.0
