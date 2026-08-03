"""Redis cache: TTL handling, graceful degradation, hit/miss accounting."""
from app.domains.market_data.cache import DEFAULT_TTLS, MarketCache
from app.domains.market_data.observability import MetricsCollector


class FakeRedis:
    """Minimal in-memory stand-in for redis-py."""

    def __init__(self, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.broken = broken

    def get(self, key: str):  # noqa: ANN201
        if self.broken:
            raise ConnectionError("redis down")
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.broken:
            raise ConnectionError("redis down")
        self.store[key] = value
        self.ttls[key] = ttl

    def delete(self, key: str) -> None:
        if self.broken:
            raise ConnectionError("redis down")
        self.store.pop(key, None)


def test_roundtrip() -> None:
    cache = MarketCache(FakeRedis())
    cache.set("latest_price", 123.45, "TCS", "NSE")
    assert cache.get("latest_price", "TCS", "NSE") == 123.45


def test_miss_returns_none() -> None:
    assert MarketCache(FakeRedis()).get("latest_price", "NOPE", "NSE") is None


def test_no_redis_degrades_to_noop() -> None:
    cache = MarketCache(None)
    assert cache.available is False
    cache.set("latest_price", 1.0, "TCS", "NSE")       # must not raise
    assert cache.get("latest_price", "TCS", "NSE") is None


def test_broken_redis_does_not_raise() -> None:
    cache = MarketCache(FakeRedis(broken=True))
    cache.set("latest_price", 1.0, "TCS", "NSE")       # swallowed
    assert cache.get("latest_price", "TCS", "NSE") is None
    cache.invalidate("latest_price", "TCS", "NSE")


def test_configured_ttl_applied() -> None:
    redis = FakeRedis()
    cache = MarketCache(redis)
    cache.set("active_instruments", ["TCS"], "NSE")
    key = "md:active_instruments:NSE"
    assert redis.ttls[key] == DEFAULT_TTLS["active_instruments"]


def test_ttl_override() -> None:
    redis = FakeRedis()
    MarketCache(redis).set("latest_price", 1.0, "TCS", ttl=999)
    assert redis.ttls["md:latest_price:TCS"] == 999


def test_invalidate_removes_entry() -> None:
    cache = MarketCache(FakeRedis())
    cache.set("latest_price", 1.0, "TCS", "NSE")
    cache.invalidate("latest_price", "TCS", "NSE")
    assert cache.get("latest_price", "TCS", "NSE") is None


def test_hit_and_miss_are_recorded() -> None:
    metrics = MetricsCollector()
    cache = MarketCache(FakeRedis(), metrics=metrics)
    cache.set("latest_price", 1.0, "TCS", "NSE")
    cache.get("latest_price", "TCS", "NSE")     # hit
    cache.get("latest_price", "OTHER", "NSE")   # miss
    counters = metrics.snapshot()["counters"]
    assert any("cache_hit" in k for k in counters)
    assert any("cache_miss" in k for k in counters)
