"""Unit tests for SignalArbitrationEngine."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domains.portfolio.arbitration import SignalArbitrationEngine
from app.domains.portfolio.enums import ArbitrationMethod
from app.domains.portfolio.schemas import SignalRankingScore
from app.domains.strategies.enums import SignalDirection, SignalType
from app.domains.strategies.schemas import TradingSignal
from app.domains.trading.enums import OrderSide


def create_signal(
    inst_id: uuid.UUID,
    symbol: str,
    direction: SignalDirection,
    confidence: float,
    strategy_id: str,
    entry: Decimal = Decimal("100.00"),
    sl: Decimal = Decimal("95.00"),
    tp: Decimal = Decimal("110.00"),
) -> TradingSignal:
    return TradingSignal(
        signal_id=uuid.uuid4(),
        strategy_id=strategy_id,
        instrument_id=inst_id,
        symbol=symbol,
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        signal_type=SignalType.entry_long,
        direction=direction,
        confidence=confidence,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
    )


def test_arbitration_no_conflict_single_buy():
    engine = SignalArbitrationEngine()
    inst = uuid.uuid4()
    sig = create_signal(inst, "TCS", SignalDirection.long, 0.80, "strat_a")

    dec = engine.arbitrate(inst, [sig])
    assert dec.winning_side == OrderSide.buy
    assert dec.blended_confidence == 0.80
    assert dec.blended_entry_price == Decimal("100.00")
    assert dec.conflict_type == "NO_CONFLICT"


def test_arbitration_same_side_consensus_blending():
    engine = SignalArbitrationEngine()
    inst = uuid.uuid4()
    sig1 = create_signal(
        inst, "TCS", SignalDirection.long, 0.60, "strat_a",
        entry=Decimal("100.00"), sl=Decimal("94.00"), tp=Decimal("110.00")
    )
    sig2 = create_signal(
        inst, "TCS", SignalDirection.long, 0.90, "strat_b",
        entry=Decimal("102.00"), sl=Decimal("97.00"), tp=Decimal("115.00")
    )

    dec = engine.arbitrate(inst, [sig1, sig2])
    assert dec.winning_side == OrderSide.buy
    assert len(dec.selected_signals) == 2
    # Confidence weighted stop loss: (94*0.6 + 97*0.9) / 1.5 = (56.4 + 87.3) / 1.5 = 143.7 / 1.5 = 95.8
    assert dec.blended_stop_loss == Decimal("95.8000")


def test_arbitration_buy_vs_sell_net_confidence():
    engine = SignalArbitrationEngine(
        method=ArbitrationMethod.net_confidence_weighted,
        neutral_threshold=0.10,
    )
    inst = uuid.uuid4()
    sig_buy = create_signal(inst, "INFY", SignalDirection.long, 0.90, "strat_trend")
    sig_sell = create_signal(inst, "INFY", SignalDirection.short, 0.50, "strat_mean_rev")

    dec = engine.arbitrate(inst, [sig_buy, sig_sell])
    assert dec.winning_side == OrderSide.buy
    assert dec.conflict_type == "BUY_VS_SELL_RESOLVED"
    assert sig_sell.signal_id in dec.discarded_signals
    assert sig_buy.signal_id in dec.selected_signals


def test_arbitration_buy_vs_sell_neutralized():
    engine = SignalArbitrationEngine(
        method=ArbitrationMethod.net_confidence_weighted,
        neutral_threshold=0.10,
    )
    inst = uuid.uuid4()
    # Delta is 0.05 < 0.10 threshold -> Neutralized
    sig_buy = create_signal(inst, "INFY", SignalDirection.long, 0.85, "strat_trend")
    sig_sell = create_signal(inst, "INFY", SignalDirection.short, 0.80, "strat_mean_rev")

    dec = engine.arbitrate(inst, [sig_buy, sig_sell])
    assert dec.winning_side is None
    assert dec.conflict_type == "BUY_VS_SELL_BALANCED"
    assert len(dec.discarded_signals) == 2
    assert "neutralized" in dec.reason.lower()


def test_arbitration_highest_rank_wins():
    engine = SignalArbitrationEngine(method=ArbitrationMethod.highest_ranking_wins)
    inst = uuid.uuid4()
    sig_buy = create_signal(inst, "WIPRO", SignalDirection.long, 0.60, "strat_low_rank")
    sig_sell = create_signal(inst, "WIPRO", SignalDirection.short, 0.90, "strat_top_rank")

    ranking_scores = {
        sig_buy.signal_id: SignalRankingScore(
            signal_id=sig_buy.signal_id,
            instrument_id=inst,
            symbol="WIPRO",
            strategy_id="strat_low_rank",
            direction=SignalDirection.long,
            composite_score=0.45,
            rank=5,
            explanation="Rank 5",
        ),
        sig_sell.signal_id: SignalRankingScore(
            signal_id=sig_sell.signal_id,
            instrument_id=inst,
            symbol="WIPRO",
            strategy_id="strat_top_rank",
            direction=SignalDirection.short,
            composite_score=0.88,
            rank=1,
            explanation="Rank 1",
        ),
    }

    dec = engine.arbitrate(inst, [sig_buy, sig_sell], ranking_scores=ranking_scores)
    assert dec.winning_side == OrderSide.sell
    assert dec.conflict_type == "BUY_VS_SELL_HIGHEST_RANK"
    assert dec.selected_signals == [sig_sell.signal_id]
