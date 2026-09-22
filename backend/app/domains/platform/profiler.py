"""Performance Profiler and Telemetry Engine for Low-Latency Execution Auditing."""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LatencyPercentiles(BaseModel):
    """Percentile distribution metrics for execution latencies."""
    sample_count: int
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0


class ThroughputStats(BaseModel):
    """Cumulative throughput counters and rates."""
    total_cycles_executed: int = 0
    total_signals_evaluated: int = 0
    total_orders_submitted: int = 0
    total_orders_filled: int = 0
    orders_per_second: float = 0.0
    signals_per_second: float = 0.0


class ResourceStats(BaseModel):
    """Process CPU and Memory consumption statistics."""
    cpu_percent: float = 0.0
    memory_rss_mb: float = 0.0


class PerformanceSnapshot(BaseModel):
    """Comprehensive performance and telemetry snapshot."""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    cycle_latency: LatencyPercentiles
    stage_latencies: dict[str, LatencyPercentiles] = Field(default_factory=dict)
    throughput: ThroughputStats
    resources: ResourceStats


class PerformanceProfiler:
    """Thread-safe performance telemetry collector computing rolling percentiles and throughput."""

    def __init__(self, window_size: int = 2000) -> None:
        self._window_size = window_size
        self._cycle_latencies: deque[float] = deque(maxlen=window_size)
        self._stage_latencies: dict[str, deque[float]] = {}

        self._total_cycles = 0
        self._total_signals = 0
        self._total_orders_submitted = 0
        self._total_orders_filled = 0
        self._start_time = time.time()

        self._lock = threading.Lock()

    def record_cycle(
        self,
        total_duration_ms: float,
        stage_latencies: dict[str, float],
        signals_count: int = 0,
        orders_submitted: int = 0,
        orders_filled: int = 0,
    ) -> None:
        with self._lock:
            self._cycle_latencies.append(total_duration_ms)
            self._total_cycles += 1
            self._total_signals += signals_count
            self._total_orders_submitted += orders_submitted
            self._total_orders_filled += orders_filled

            for stage, lat in stage_latencies.items():
                if stage not in self._stage_latencies:
                    self._stage_latencies[stage] = deque(maxlen=self._window_size)
                self._stage_latencies[stage].append(lat)

    @staticmethod
    def _compute_percentiles(samples: list[float]) -> LatencyPercentiles:
        if not samples:
            return LatencyPercentiles(sample_count=0)

        sorted_s = sorted(samples)
        n = len(sorted_s)
        mean_val = sum(sorted_s) / n
        min_val = sorted_s[0]
        max_val = sorted_s[-1]

        def get_p(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_s[int(k)]
            return sorted_s[int(f)] * (c - k) + sorted_s[int(c)] * (k - f)

        return LatencyPercentiles(
            sample_count=n,
            min_ms=round(min_val, 4),
            max_ms=round(max_val, 4),
            mean_ms=round(mean_val, 4),
            p50_ms=round(get_p(0.50), 4),
            p95_ms=round(get_p(0.95), 4),
            p99_ms=round(get_p(0.99), 4),
        )

    def _get_resource_stats(self) -> ResourceStats:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024.0 * 1024.0)
            cpu_pct = process.cpu_percent(interval=None)
            return ResourceStats(cpu_percent=round(cpu_pct, 2), memory_rss_mb=round(mem_mb, 2))
        except ImportError:
            return ResourceStats(cpu_percent=0.0, memory_rss_mb=0.0)

    def get_snapshot(self) -> PerformanceSnapshot:
        with self._lock:
            cycle_samples = list(self._cycle_latencies)
            stage_samples = {k: list(v) for k, v in self._stage_latencies.items()}
            tot_cyc = self._total_cycles
            tot_sig = self._total_signals
            tot_sub = self._total_orders_submitted
            tot_fill = self._total_orders_filled

        elapsed = max(1.0, time.time() - self._start_time)
        cycle_perc = self._compute_percentiles(cycle_samples)
        stage_percs = {k: self._compute_percentiles(v) for k, v in stage_samples.items()}

        throughput = ThroughputStats(
            total_cycles_executed=tot_cyc,
            total_signals_evaluated=tot_sig,
            total_orders_submitted=tot_sub,
            total_orders_filled=tot_fill,
            orders_per_second=round(tot_sub / elapsed, 4),
            signals_per_second=round(tot_sig / elapsed, 4),
        )

        return PerformanceSnapshot(
            cycle_latency=cycle_perc,
            stage_latencies=stage_percs,
            throughput=throughput,
            resources=self._get_resource_stats(),
        )

    def reset(self) -> None:
        with self._lock:
            self._cycle_latencies.clear()
            self._stage_latencies.clear()
            self._total_cycles = 0
            self._total_signals = 0
            self._total_orders_submitted = 0
            self._total_orders_filled = 0
            self._start_time = time.time()


global_performance_profiler = PerformanceProfiler()
