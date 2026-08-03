"""Metrics collection used by the market data health endpoints."""
from app.domains.market_data.observability import MetricsCollector


def test_counters_accumulate() -> None:
    m = MetricsCollector()
    m.incr("requests", provider="mock")
    m.incr("requests", value=2, provider="mock")
    assert m.snapshot()["counters"]["requests[provider=mock]"] == 3


def test_labels_separate_series() -> None:
    m = MetricsCollector()
    m.incr("requests", provider="a")
    m.incr("requests", provider="b")
    counters = m.snapshot()["counters"]
    assert counters["requests[provider=a]"] == 1
    assert counters["requests[provider=b]"] == 1


def test_gauges_overwrite() -> None:
    m = MetricsCollector()
    m.gauge("provider_available", 1.0, provider="mock")
    m.gauge("provider_available", 0.0, provider="mock")
    assert m.snapshot()["gauges"]["provider_available[provider=mock]"] == 0.0


def test_latency_stats() -> None:
    m = MetricsCollector()
    for value in (10, 20, 30, 40):
        m.observe_latency("provider_latency", value, provider="mock")
    stats = m.snapshot()["latency"]["provider_latency[provider=mock]"]
    assert stats["count"] == 4
    assert stats["avg_ms"] == 25.0
    assert stats["p95_ms"] >= 30.0


def test_timed_context_manager_records() -> None:
    m = MetricsCollector()
    with m.timed("sync_duration", exchange="NSE"):
        pass
    assert m.snapshot()["latency"]["sync_duration[exchange=NSE]"]["count"] == 1


def test_broken_redis_backend_falls_back_to_memory() -> None:
    class BrokenRedis:
        def hincrbyfloat(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
            raise ConnectionError("down")

        def hset(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
            raise ConnectionError("down")

    m = MetricsCollector(BrokenRedis())
    m.incr("requests")           # must not raise
    m.gauge("freshness", 1.0)
    assert m.snapshot()["counters"]["requests"] == 1
