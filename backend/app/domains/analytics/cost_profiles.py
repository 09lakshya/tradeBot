"""Enhanced Trading Cost Profile Engine with versioning, persistence, and broker-specific templates."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.analytics.models import CostProfileRecord
from app.domains.analytics.schemas import (
    CostComparisonResponse,
    CostProfileCreateRequest,
    DetailedCostBreakdown,
)
from app.domains.market_data.enums import Exchange
from app.domains.platform.logging import get_structured_logger
from app.domains.trading.cost_engine import CostEngine, TradingCostProfile
from app.domains.trading.enums import OrderSide, ProductType

log = get_structured_logger(__name__)


# ── Built-in Indian Market Cost Profile Templates ──────────────────────────────

BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "ideal": {
        "profile_name": "ideal",
        "brokerage_flat": "0", "brokerage_pct": "0", "brokerage_cap": "0",
        "brokerage_delivery_zero": True,
        "stt_delivery_buy_pct": "0", "stt_delivery_sell_pct": "0",
        "stt_intraday_buy_pct": "0", "stt_intraday_sell_pct": "0",
        "exchange_txn_nse_pct": "0", "exchange_txn_bse_pct": "0",
        "sebi_turnover_pct": "0",
        "stamp_duty_delivery_buy_pct": "0", "stamp_duty_delivery_sell_pct": "0",
        "stamp_duty_intraday_buy_pct": "0", "stamp_duty_intraday_sell_pct": "0",
        "gst_pct": "0",
    },
    "indian_equity_delivery": {
        "profile_name": "indian_equity_delivery",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": True,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "indian_intraday": {
        "profile_name": "indian_intraday",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0000", "stt_delivery_sell_pct": "0.0000",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00003", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "indian_futures": {
        "profile_name": "indian_futures",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0000", "stt_delivery_sell_pct": "0.0000",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.000125",
        "exchange_txn_nse_pct": "0.0000190", "exchange_txn_bse_pct": "0.0000190",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00002", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00002", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "indian_options": {
        "profile_name": "indian_options",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0000", "stt_delivery_sell_pct": "0.0000",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.000625",
        "exchange_txn_nse_pct": "0.0000500", "exchange_txn_bse_pct": "0.0000500",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00003", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "zerodha_2026_v1": {
        "profile_name": "zerodha_2026_v1",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": True,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "groww_2026_v1": {
        "profile_name": "groww_2026_v1",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0005", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": True,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "upstox_2026_v1": {
        "profile_name": "upstox_2026_v1",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0005", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "angelone_2026_v1": {
        "profile_name": "angelone_2026_v1",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.00025", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": True,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "icici_2026_v1": {
        "profile_name": "icici_2026_v1",
        "brokerage_flat": "0.0000", "brokerage_pct": "0.0055", "brokerage_cap": "9999.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
    "kotakneo_2026_v1": {
        "profile_name": "kotakneo_2026_v1",
        "brokerage_flat": "20.0000", "brokerage_pct": "0.0003", "brokerage_cap": "20.0000",
        "brokerage_delivery_zero": False,
        "stt_delivery_buy_pct": "0.0010", "stt_delivery_sell_pct": "0.0010",
        "stt_intraday_buy_pct": "0.0000", "stt_intraday_sell_pct": "0.00025",
        "exchange_txn_nse_pct": "0.0000297", "exchange_txn_bse_pct": "0.0000375",
        "sebi_turnover_pct": "0.0000010",
        "stamp_duty_delivery_buy_pct": "0.00015", "stamp_duty_delivery_sell_pct": "0.0000",
        "stamp_duty_intraday_buy_pct": "0.00003", "stamp_duty_intraday_sell_pct": "0.0000",
        "gst_pct": "0.1800",
    },
}


def _profile_data_to_trading_cost_profile(name: str, data: dict[str, Any]) -> TradingCostProfile:
    """Convert a profile data dict to the production CostEngine's TradingCostProfile."""
    return TradingCostProfile(
        profile_name=name,
        brokerage_flat=Decimal(str(data.get("brokerage_flat", "20.0000"))),
        brokerage_pct=Decimal(str(data.get("brokerage_pct", "0.0003"))),
        brokerage_cap=Decimal(str(data.get("brokerage_cap", "20.0000"))),
        brokerage_delivery_zero=data.get("brokerage_delivery_zero", True),
        stt_delivery_buy_pct=Decimal(str(data.get("stt_delivery_buy_pct", "0.0010"))),
        stt_delivery_sell_pct=Decimal(str(data.get("stt_delivery_sell_pct", "0.0010"))),
        stt_intraday_buy_pct=Decimal(str(data.get("stt_intraday_buy_pct", "0.0000"))),
        stt_intraday_sell_pct=Decimal(str(data.get("stt_intraday_sell_pct", "0.00025"))),
        exchange_txn_nse_pct=Decimal(str(data.get("exchange_txn_nse_pct", "0.0000297"))),
        exchange_txn_bse_pct=Decimal(str(data.get("exchange_txn_bse_pct", "0.0000375"))),
        sebi_turnover_pct=Decimal(str(data.get("sebi_turnover_pct", "0.0000010"))),
        stamp_duty_delivery_buy_pct=Decimal(str(data.get("stamp_duty_delivery_buy_pct", "0.00015"))),
        stamp_duty_delivery_sell_pct=Decimal(str(data.get("stamp_duty_delivery_sell_pct", "0.0000"))),
        stamp_duty_intraday_buy_pct=Decimal(str(data.get("stamp_duty_intraday_buy_pct", "0.00003"))),
        stamp_duty_intraday_sell_pct=Decimal(str(data.get("stamp_duty_intraday_sell_pct", "0.0000"))),
        gst_pct=Decimal(str(data.get("gst_pct", "0.1800"))),
    )


class CostProfileManager:
    """Manages versioned cost profiles with persistence and bridges to the production CostEngine."""

    def __init__(self) -> None:
        self._cost_engine = CostEngine(default_profile="default")
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all built-in Indian market profiles with the CostEngine."""
        for name, data in BUILTIN_PROFILES.items():
            profile = _profile_data_to_trading_cost_profile(name, data)
            CostEngine.register_profile(profile)

    def create_profile(
        self,
        db: Session,
        request: CostProfileCreateRequest,
    ) -> CostProfileRecord:
        """Create and persist a custom cost profile."""
        profile_data = request.model_dump(
            exclude={"profile_name", "version", "description"},
            mode="json",
        )
        record = CostProfileRecord(
            profile_name=request.profile_name,
            version=request.version,
            profile_data=profile_data,
            description=request.description,
            is_active=True,
        )
        db.add(record)
        db.flush()

        # Register with in-memory CostEngine
        versioned_name = f"{request.profile_name}_{request.version}"
        tcp = _profile_data_to_trading_cost_profile(versioned_name, profile_data)
        CostEngine.register_profile(tcp)

        log.info("cost_profile_created", profile=request.profile_name, version=request.version)
        return record

    def get_profile(
        self,
        db: Session,
        profile_name: str,
        version: str | None = None,
    ) -> CostProfileRecord | None:
        """Retrieve a cost profile by name and optional version."""
        stmt = select(CostProfileRecord).where(
            CostProfileRecord.profile_name == profile_name
        )
        if version:
            stmt = stmt.where(CostProfileRecord.version == version)
        else:
            stmt = stmt.where(CostProfileRecord.is_active.is_(True))
        stmt = stmt.limit(1)
        return db.execute(stmt).scalar_one_or_none()

    def list_profiles(self, db: Session) -> list[CostProfileRecord]:
        """List all persisted cost profiles."""
        stmt = select(CostProfileRecord).order_by(CostProfileRecord.profile_name)
        return list(db.execute(stmt).scalars().all())

    def get_builtin_profiles(self) -> dict[str, dict[str, Any]]:
        """Return all built-in profile templates."""
        return dict(BUILTIN_PROFILES)

    def calculate_trade_costs(
        self,
        side: OrderSide,
        product_type: ProductType,
        exchange: Exchange,
        quantity: Decimal,
        price: Decimal,
        profile_name: str = "indian_equity_delivery",
    ) -> DetailedCostBreakdown:
        """Calculate detailed cost breakdown for a trade using the CostEngine."""
        breakdown = self._cost_engine.calculate_cost(
            side=side,
            product_type=product_type,
            exchange=exchange,
            quantity=quantity,
            price=price,
            profile_name=profile_name,
        )
        return DetailedCostBreakdown(
            brokerage=breakdown.brokerage,
            stt=breakdown.stt,
            exchange_charges=breakdown.exchange_charges,
            gst=breakdown.gst,
            stamp_duty=breakdown.stamp_duty,
            sebi_charges=breakdown.sebi_charges,
            broker_total=breakdown.brokerage,
            government_total=breakdown.stt + breakdown.stamp_duty + breakdown.sebi_charges,
            execution_total=Decimal("0.0000"),  # slippage tracked separately
            total_charges=breakdown.total_charges,
        )

    def get_cost_comparison(
        self,
        quantity: Decimal,
        price: Decimal,
        profile_names: list[str],
        side: OrderSide = OrderSide.buy,
        product_type: ProductType = ProductType.cnc,
        exchange: Exchange = Exchange.NSE,
    ) -> CostComparisonResponse:
        """Compare costs across multiple profiles."""
        profiles_result: dict[str, DetailedCostBreakdown] = {}
        for name in profile_names:
            try:
                profiles_result[name] = self.calculate_trade_costs(
                    side=side, product_type=product_type, exchange=exchange,
                    quantity=quantity, price=price, profile_name=name,
                )
            except Exception:
                log.warning("cost_comparison_profile_failed", profile=name)
                continue
        return CostComparisonResponse(
            quantity=quantity,
            price=price,
            turnover=quantity * price,
            profiles=profiles_result,
        )
