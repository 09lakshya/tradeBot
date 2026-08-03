"""Corporate Action engine.

Computes and applies back-adjustment so historical prices stay continuous across
capital events. Without this a 1:2 split reads as a 50% overnight crash and every
strategy/backtest built on the series is wrong.

Convention: bars *strictly before* an action's ex-date are multiplied by that
action's factor; factors compound backwards through time (standard back-adjustment,
so the most recent price always equals the traded price).

Price-affecting: split, bonus, dividend, rights.
Metadata-only (no price adjustment): buyback, merger, spinoff, symbol_change,
delisting — these are handled as instrument-master lifecycle events.
"""
from dataclasses import dataclass
from datetime import date

from app.core.logging import get_logger
from app.domains.market_data.enums import CorporateActionType
from app.domains.market_data.schemas import CorporateActionDTO, OHLCVBar

log = get_logger(__name__)

#: Actions that change the price series.
PRICE_AFFECTING = {
    CorporateActionType.split,
    CorporateActionType.bonus,
    CorporateActionType.dividend,
    CorporateActionType.rights,
}

#: Actions that affect the Instrument Master rather than the price series.
LIFECYCLE = {
    CorporateActionType.merger,
    CorporateActionType.spinoff,
    CorporateActionType.symbol_change,
    CorporateActionType.delisting,
    CorporateActionType.buyback,
}


@dataclass
class AdjustmentFactor:
    ex_date: date
    factor: float
    action_type: CorporateActionType


class CorporateActionEngine:
    """Pure computation — no DB access, so it is trivially testable."""

    def factor_for(
        self, action: CorporateActionDTO, reference_close: float | None = None
    ) -> float:
        """Multiplier applied to bars *before* ``action.ex_date``. 1.0 = no change."""
        kind = action.action_type

        if kind in (CorporateActionType.split, CorporateActionType.bonus):
            # ratio_from:ratio_to — 1:2 split -> pre-split prices halve.
            if not action.ratio_from or not action.ratio_to:
                log.warning("corp_action_missing_ratio", action=kind.value)
                return 1.0
            if kind is CorporateActionType.bonus:
                # Bonus a:b -> holder gets `a` extra for every `b` held.
                return action.ratio_to / (action.ratio_to + action.ratio_from)
            return action.ratio_from / action.ratio_to

        if kind is CorporateActionType.dividend:
            if not action.amount or not reference_close or reference_close <= 0:
                return 1.0
            factor = (reference_close - action.amount) / reference_close
            return max(factor, 0.0001)   # guard against absurd/erroneous dividends

        if kind is CorporateActionType.rights:
            # Theoretical ex-rights price adjustment needs subscription terms;
            # fall back to no adjustment rather than guessing wrong.
            if not action.ratio_from or not action.ratio_to or not action.amount:
                return 1.0
            if not reference_close or reference_close <= 0:
                return 1.0
            n_new, n_old = action.ratio_from, action.ratio_to
            terp = ((n_old * reference_close) + (n_new * action.amount)) / (n_old + n_new)
            return terp / reference_close

        return 1.0

    def adjust(
        self, bars: list[OHLCVBar], actions: list[CorporateActionDTO]
    ) -> list[OHLCVBar]:
        """Return a new bar list with ``adjusted_close`` and adjusted OHLC.

        Bars must be chronologically ascending. Non-price-affecting actions are ignored.
        """
        if not bars:
            return []
        relevant = sorted(
            (a for a in actions if a.action_type in PRICE_AFFECTING),
            key=lambda a: a.ex_date,
        )
        if not relevant:
            return [b.model_copy(update={"adjusted_close": b.adjusted_close or b.close})
                    for b in bars]

        ordered = sorted(bars, key=lambda b: b.ts)
        closes = {b.ts.date(): b.close for b in ordered}

        # Compute each action's factor using the last close before its ex-date.
        factors: list[AdjustmentFactor] = []
        for action in relevant:
            prior = [d for d in closes if d < action.ex_date]
            ref = closes[max(prior)] if prior else None
            factors.append(AdjustmentFactor(
                ex_date=action.ex_date,
                factor=self.factor_for(action, ref),
                action_type=action.action_type,
            ))

        adjusted: list[OHLCVBar] = []
        for bar in ordered:
            # Compound every factor whose ex-date is after this bar.
            cumulative = 1.0
            for f in factors:
                if bar.ts.date() < f.ex_date:
                    cumulative *= f.factor
            if cumulative == 1.0:
                adjusted.append(bar.model_copy(
                    update={"adjusted_close": bar.adjusted_close or bar.close}
                ))
                continue
            adjusted.append(bar.model_copy(update={
                "open": round(bar.open * cumulative, 4),
                "high": round(bar.high * cumulative, 4),
                "low": round(bar.low * cumulative, 4),
                "close": round(bar.close * cumulative, 4),
                "adjusted_close": round(bar.close * cumulative, 4),
                # Volume scales inversely for share-count events.
                "volume": int(bar.volume / cumulative) if cumulative > 0 else bar.volume,
            }))
        return adjusted
