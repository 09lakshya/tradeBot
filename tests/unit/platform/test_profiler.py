"""Unit tests for Performance Profiler and Telemetry Statistics."""
from app.domains.platform.profiler import PerformanceProfiler


def test_profiler_percentiles_and_throughput():
    profiler = PerformanceProfiler(window_size=100)

    for i in range(1, 101):
        profiler.record_cycle(
            total_duration_ms=float(i),
            stage_latencies={"eval": float(i) * 0.5, "oms": float(i) * 0.3},
            signals_count=5,
            orders_submitted=2,
            orders_filled=2,
        )

    snap = profiler.get_snapshot()
    assert snap.cycle_latency.sample_count == 100
    assert snap.cycle_latency.min_ms == 1.0
    assert snap.cycle_latency.max_ms == 100.0
    assert snap.cycle_latency.mean_ms == 50.5
    assert snap.cycle_latency.p50_ms == 50.5
    assert snap.cycle_latency.p95_ms == 95.05
    assert snap.cycle_latency.p99_ms == 99.01

    assert snap.throughput.total_cycles_executed == 100
    assert snap.throughput.total_signals_evaluated == 500
    assert snap.throughput.total_orders_submitted == 200
    assert snap.throughput.total_orders_filled == 200

    assert "eval" in snap.stage_latencies
    assert snap.stage_latencies["eval"].sample_count == 100
