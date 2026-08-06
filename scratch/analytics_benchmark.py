"""Benchmark script measuring performance and throughput of Phase 9 Analytics & Trade Journal subsystems."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
import app.models  # noqa: F401

from app.domains.analytics.alerts import AlertEngine
from app.domains.analytics.attribution import StrategyAttributionService
from app.domains.analytics.cost_profiles import CostProfileManager
from app.domains.analytics.equity_curve import EquityCurveService
from app.domains.analytics.performance import PerformanceAnalyticsService
from app.domains.analytics.regime import MarketRegimeAnalyzer
from app.domains.analytics.schemas import TradeJournalFilterRequest
from app.domains.analytics.trade_journal import TradeJournalService
from app.domains.market_data.enums import Exchange
from app.domains.trading.enums import OrderSide, ProductType
from app.domains.trading.models import Portfolio


def setup_benchmark_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    return maker()


def main():
    db = setup_benchmark_db()
    journal = TradeJournalService()
    cost_mgr = CostProfileManager()
    eq_service = EquityCurveService()
    perf_service = PerformanceAnalyticsService()
    attr_service = StrategyAttributionService()
    regime_service = MarketRegimeAnalyzer()
    alert_engine = AlertEngine()

    portfolio = Portfolio(name="Bench", initial_capital=Decimal("1000000.0000"), cash_balance=Decimal("1000000.0000"))
    db.add(portfolio)
    db.flush()

    print("=" * 80)
    print("PHASE 9 ANALYTICS BENCHMARK")
    print("=" * 80)

    # 1. Cost Calculations Benchmark
    n_costs = 50000
    t0 = time.perf_counter()
    for _ in range(n_costs):
        cost_mgr.calculate_trade_costs(
            side=OrderSide.buy, product_type=ProductType.cnc, exchange=Exchange.NSE,
            quantity=Decimal("100.0000"), price=Decimal("1500.0000"), profile_name="zerodha_2026_v1",
        )
    t1 = time.perf_counter()
    elapsed_costs = t1 - t0
    cost_ops = n_costs / elapsed_costs
    cost_lat = (elapsed_costs / n_costs) * 1e6
    print(f"1. Cost Calculation Engine:       {cost_ops:,.0f} ops/sec  | Mean Latency: {cost_lat:.2f} µs/op")

    # 2. Trade Journal Recording Benchmark
    n_trades = 5000
    now = datetime.now(timezone.utc)
    inst_id = uuid.uuid4()
    cost_dict = {"total_charges": "45.00"}

    t0 = time.perf_counter()
    for i in range(n_trades):
        journal.record_trade(
            db, portfolio_id=portfolio.id, instrument_id=inst_id,
            strategy_id=f"strat_{i % 5}", symbol=f"SYM_{i % 20}",
            entry_timestamp=now - timedelta(minutes=n_trades - i),
            exit_timestamp=now - timedelta(minutes=n_trades - i - 1),
            entry_price=Decimal("1000.0000"), exit_price=Decimal("1020.0000"),
            quantity=Decimal("50.0000"), cost_breakdown=cost_dict,
        )
    db.commit()
    t1 = time.perf_counter()
    elapsed_rec = t1 - t0
    rec_ops = n_trades / elapsed_rec
    rec_lat = (elapsed_rec / n_trades) * 1e6
    print(f"2. Trade Journal Recording:      {rec_ops:,.0f} recs/sec | Mean Latency: {rec_lat:.2f} µs/record")

    # 3. Trade Journal Query Benchmark
    n_queries = 1000
    t0 = time.perf_counter()
    for _ in range(n_queries):
        req = TradeJournalFilterRequest(portfolio_id=portfolio.id, strategy_id="strat_0", limit=100)
        journal.get_trades(db, req)
    t1 = time.perf_counter()
    elapsed_q = t1 - t0
    q_ops = n_queries / elapsed_q
    q_lat = (elapsed_q / n_queries) * 1e3
    print(f"3. Trade Journal Filter Query:   {q_ops:,.0f} ops/sec  | Mean Latency: {q_lat:.2f} ms/query")

    # 4. Equity Snapshot Recording Benchmark
    n_snapshots = 1000
    t0 = time.perf_counter()
    for i in range(n_snapshots):
        eq_service.record_snapshot(
            db, portfolio_id=portfolio.id,
            timestamp=now - timedelta(days=n_snapshots - i),
            gross_equity=Decimal("1000000.0000") + Decimal(str(i * 100)),
            net_equity=Decimal("1000000.0000") + Decimal(str(i * 90)),
            cash_balance=Decimal("500000.0000"), invested_value=Decimal("500000.0000"),
        )
    db.commit()
    t1 = time.perf_counter()
    elapsed_snap = t1 - t0
    snap_ops = n_snapshots / elapsed_snap
    snap_lat = (elapsed_snap / n_snapshots) * 1e6
    print(f"4. Equity Curve Recording:       {snap_ops:,.0f} snaps/sec| Mean Latency: {snap_lat:.2f} µs/snapshot")

    # 5. Gross vs Net Performance Calculation
    t0 = time.perf_counter()
    perf_service.calculate_gross_net_report(db, portfolio.id)
    t1 = time.perf_counter()
    perf_lat = (t1 - t0) * 1e3
    print(f"5. Gross/Net Performance Calc:   Mean Latency: {perf_lat:.2f} ms")

    # 6. Strategy Attribution Calculation
    t0 = time.perf_counter()
    attr_service.get_all_strategy_attributions(db, portfolio.id)
    t1 = time.perf_counter()
    attr_lat = (t1 - t0) * 1e3
    print(f"6. Strategy Attribution Engine: Mean Latency: {attr_lat:.2f} ms")

    # 7. Alert Evaluation Benchmark
    t0 = time.perf_counter()
    alert_engine.evaluate_alerts(db, portfolio.id)
    t1 = time.perf_counter()
    alert_lat = (t1 - t0) * 1e3
    print(f"7. Alert Engine Evaluation:     Mean Latency: {alert_lat:.2f} ms")

    print("=" * 80)


if __name__ == "__main__":
    main()
