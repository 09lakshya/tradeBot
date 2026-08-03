"""Known-answer tests against the golden OHLCV fixture.

These prove the pipeline produces *correct* numbers, not merely that it runs —
the distinction that matters for a backtester built on top of this data.
"""
import json
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from app.domains.market_data.corporate_actions import CorporateActionEngine
from app.domains.market_data.enums import Timeframe
from app.domains.market_data.schemas import CorporateActionDTO, OHLCVBar
from app.domains.market_data.validation import DataQualityValidator

FIXTURE = Path(__file__).parents[2] / "fixtures" / "golden_ohlcv.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bars(golden: dict) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            ts=datetime.fromisoformat(b["ts"]), open=b["open"], high=b["high"],
            low=b["low"], close=b["close"], volume=b["volume"],
        )
        for b in golden["bars"]
    ]


def test_golden_bars_pass_validation(golden: dict) -> None:
    result = DataQualityValidator().validate(_bars(golden), Timeframe.d1)
    assert len(result.valid) == len(golden["bars"])
    assert result.rejected_count == 0


def test_golden_split_adjustment_matches_expected(golden: dict) -> None:
    actions = [
        CorporateActionDTO(
            action_type=ca["action_type"],
            ex_date=date.fromisoformat(ca["ex_date"]),
            ratio_from=ca["ratio_from"], ratio_to=ca["ratio_to"],
        )
        for ca in golden["corporate_actions"]
    ]
    adjusted = CorporateActionEngine().adjust(_bars(golden), actions)
    actual = [round(b.close, 2) for b in adjusted]
    assert actual == pytest.approx(golden["expected_adjusted_closes"])


def test_golden_series_is_continuous_after_adjustment(golden: dict) -> None:
    """The split must not leave a >20% single-day gap in the adjusted series."""
    actions = [
        CorporateActionDTO(
            action_type=ca["action_type"], ex_date=date.fromisoformat(ca["ex_date"]),
            ratio_from=ca["ratio_from"], ratio_to=ca["ratio_to"],
        )
        for ca in golden["corporate_actions"]
    ]
    adjusted = CorporateActionEngine().adjust(_bars(golden), actions)
    closes = [b.close for b in adjusted]
    for prev, curr in pairwise(closes):
        pct_move = abs(curr - prev) / prev
        assert pct_move < 0.20, f"discontinuity {prev} -> {curr} survived adjustment"


def test_raw_series_has_the_discontinuity_adjustment_removes(golden: dict) -> None:
    """Sanity check the fixture actually contains the split artefact."""
    closes = [b["close"] for b in golden["bars"]]
    drops = [abs(c - p) / p for p, c in pairwise(closes)]
    assert max(drops) > 0.40, "fixture should contain a raw ~50% split drop"
