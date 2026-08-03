"""Market Data observability: counters, gauges, and latency stats backed by Redis
with a thread-safe in-memory fallback so metrics never crash a request path.

Tracked (spec §8): provider latency, failed requests, retry count, rate-limit
events, cache hit rate, missing candles, sync duration, DB insert rate, data
freshness, provider availability. Surfaced through the health endpoints.
"""
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

_KEY = "md:metrics"


class MetricsCollector:
    """Best-effort metrics. Uses Redis when available; degrades to in-memory."""

    def __init__(self, redis_client: object | None = None) -> None:
        self._redis = redis_client
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._latency: dict[str, list[float]] = defaultdict(list)

    # --- counters -------------------------------------------------------
    def incr(self, metric: str, value: float = 1.0, **labels: str) -> None:
        key = _labelled(metric, labels)
        try:
            if self._redis is not None:
                self._redis.hincrbyfloat(_KEY, key, value)  # type: ignore[attr-defined]
                return
        except Exception:  # noqa: BLE001 - metrics must never break callers
            pass
        with self._lock:
            self._counters[key] += value

    def gauge(self, metric: str, value: float, **labels: str) -> None:
        key = _labelled(metric, labels)
        try:
            if self._redis is not None:
                self._redis.hset(f"{_KEY}:gauge", key, value)  # type: ignore[attr-defined]
                return
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            self._gauges[key] = value

    def observe_latency(self, metric: str, ms: float, **labels: str) -> None:
        key = _labelled(metric, labels)
        with self._lock:
            samples = self._latency[key]
            samples.append(ms)
            if len(samples) > 500:  # bounded window
                del samples[: len(samples) - 500]

    @contextmanager
    def timed(self, metric: str, **labels: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe_latency(metric, (time.perf_counter() - start) * 1000, **labels)

    # --- readout --------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latency = {
                k: {
                    "count": len(v),
                    "avg_ms": round(sum(v) / len(v), 2) if v else 0.0,
                    "p95_ms": round(_percentile(v, 95), 2) if v else 0.0,
                }
                for k, v in self._latency.items()
            }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "latency": latency,
            }


def _labelled(metric: str, labels: dict[str, str]) -> str:
    if not labels:
        return metric
    tags = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{metric}[{tags}]"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


#: Process-wide default collector (wired to Redis at app startup).
metrics = MetricsCollector()
