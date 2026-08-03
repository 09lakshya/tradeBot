"""Corporate action back-adjustment — the maths that keeps backtests honest."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.market_data.corporate_actions import CorporateActionEngine
from app.domains.market_data.enums import CorporateActionType
from app.domains.market_data.schemas import CorporateActionDTO, OHLCVBar

engine = CorporateActionEngine()
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def series(n: int = 5, price: float = 100.0) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            ts=BASE + timedelta(days=i), open=price, high=price * 1.02,
            low=price * 0.98, close=price, volume=1000,
        )
        for i in range(n)
    ]


def test_split_factor() -> None:
    action = CorporateActionDTO(
        action_type=CorporateActionType.split,
        ex_date=date(2026, 1, 3), ratio_from=1, ratio_to=2,
    )
    assert engine.factor_for(action) == pytest.approx(0.5)


def test_split_halves_prices_before_ex_date_only() -> None:
    action = CorporateActionDTO(
        action_type=CorporateActionType.split,
        ex_date=date(2026, 1, 3), ratio_from=1, ratio_to=2,
    )
    adjusted = engine.adjust(series(5), [action])
    # Bars on Jan 1-2 are pre-split -> halved; Jan 3 onwards untouched.
    assert adjusted[0].close == pytest.approx(50.0)
    assert adjusted[1].close == pytest.approx(50.0)
    assert adjusted[2].close == pytest.approx(100.0)
    assert adjusted[4].close == pytest.approx(100.0)


def test_split_scales_volume_inversely() -> None:
    action = CorporateActionDTO(
        action_type=CorporateActionType.split,
        ex_date=date(2026, 1, 3), ratio_from=1, ratio_to=2,
    )
    adjusted = engine.adjust(series(5), [action])
    assert adjusted[0].volume == 2000, "share count doubles when price halves"
    assert adjusted[2].volume == 1000


def test_bonus_factor() -> None:
    # 1:1 bonus -> one extra share per share held -> prices halve.
    action = CorporateActionDTO(
        action_type=CorporateActionType.bonus,
        ex_date=date(2026, 1, 3), ratio_from=1, ratio_to=1,
    )
    assert engine.factor_for(action) == pytest.approx(0.5)


def test_dividend_factor_uses_reference_close() -> None:
    action = CorporateActionDTO(
        action_type=CorporateActionType.dividend,
        ex_date=date(2026, 1, 3), amount=5.0,
    )
    assert engine.factor_for(action, reference_close=100.0) == pytest.approx(0.95)


def test_dividend_without_reference_is_noop() -> None:
    action = CorporateActionDTO(
        action_type=CorporateActionType.dividend, ex_date=date(2026, 1, 3), amount=5.0
    )
    assert engine.factor_for(action, reference_close=None) == pytest.approx(1.0)


def test_lifecycle_actions_do_not_adjust_prices() -> None:
    for kind in (CorporateActionType.buyback, CorporateActionType.merger,
                 CorporateActionType.spinoff, CorporateActionType.symbol_change,
                 CorporateActionType.delisting):
        action = CorporateActionDTO(action_type=kind, ex_date=date(2026, 1, 3))
        assert engine.factor_for(action) == pytest.approx(1.0)

    original = series(3)
    adjusted = engine.adjust(original, [
        CorporateActionDTO(action_type=CorporateActionType.buyback, ex_date=date(2026, 1, 2))
    ])
    assert [b.close for b in adjusted] == [b.close for b in original]


def test_multiple_actions_compound() -> None:
    actions = [
        CorporateActionDTO(action_type=CorporateActionType.split,
                           ex_date=date(2026, 1, 3), ratio_from=1, ratio_to=2),
        CorporateActionDTO(action_type=CorporateActionType.split,
                           ex_date=date(2026, 1, 5), ratio_from=1, ratio_to=2),
    ]
    adjusted = engine.adjust(series(5), actions)
    # Jan 1 sits before both splits -> 100 * 0.5 * 0.5
    assert adjusted[0].close == pytest.approx(25.0)
    # Jan 3 sits before only the second split
    assert adjusted[2].close == pytest.approx(50.0)
    # Jan 5 is on/after both
    assert adjusted[4].close == pytest.approx(100.0)


def test_missing_ratio_is_safe_noop() -> None:
    action = CorporateActionDTO(action_type=CorporateActionType.split,
                                ex_date=date(2026, 1, 3))
    assert engine.factor_for(action) == pytest.approx(1.0)


def test_adjust_empty_series() -> None:
    assert engine.adjust([], []) == []


def test_adjusted_close_always_populated() -> None:
    adjusted = engine.adjust(series(3), [])
    assert all(b.adjusted_close is not None for b in adjusted)
