"""Provider registry + failover router.

The registry maps provider names to classes and builds instances from config.
``ProviderRouter`` presents the ``MarketDataProvider`` surface but transparently
rate-limits, retries, records metrics, and fails over across a chain of providers
— so callers never know or care which source answered.
"""
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import TypeVar

from app.core.logging import get_logger
from app.domains.market_data.enums import AssetClass, Exchange, ProviderStatus, Timeframe
from app.domains.market_data.observability import MetricsCollector
from app.domains.market_data.observability import metrics as default_metrics
from app.domains.market_data.providers.base import (
    MarketDataProvider,
    ProviderError,
    ProviderRateLimitError,
)
from app.domains.market_data.providers.resilience import RateLimiter, RetryPolicy, with_retry
from app.domains.market_data.schemas import (
    CorporateActionDTO,
    InstrumentDTO,
    OHLCVResponse,
    ProviderHealth,
)

log = get_logger(__name__)
T = TypeVar("T")

# Registered lazily to avoid importing heavy provider deps until needed.
_REGISTRY: dict[str, Callable[[], MarketDataProvider]] = {}


def register(name: str, factory: Callable[[], MarketDataProvider]) -> None:
    _REGISTRY[name] = factory


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def build_provider(name: str) -> MarketDataProvider:
    if name not in _REGISTRY:
        raise KeyError(f"unknown market data provider: {name!r}")
    return _REGISTRY[name]()


def _register_builtin() -> None:
    """Register built-in providers via local imports (keeps optional deps lazy)."""
    if _REGISTRY:
        return

    def _yahoo() -> MarketDataProvider:
        from app.domains.market_data.providers.yahoo import YahooFinanceProvider
        return YahooFinanceProvider()

    def _mock() -> MarketDataProvider:
        from app.domains.market_data.providers.mock import MockProvider
        return MockProvider()

    def _alpha() -> MarketDataProvider:
        from app.domains.market_data.providers.alpha_vantage import AlphaVantageProvider
        return AlphaVantageProvider()

    def _twelve() -> MarketDataProvider:
        from app.domains.market_data.providers.twelve_data import TwelveDataProvider
        return TwelveDataProvider()

    def _finnhub() -> MarketDataProvider:
        from app.domains.market_data.providers.finnhub import FinnhubProvider
        return FinnhubProvider()

    register("yahoo", _yahoo)
    register("mock", _mock)
    register("alpha_vantage", _alpha)
    register("twelve_data", _twelve)
    register("finnhub", _finnhub)


class ProviderRouter(MarketDataProvider):
    """Ordered chain of providers with rate limiting, retry, metrics, and failover."""

    name = "router"

    def __init__(
        self,
        providers: list[MarketDataProvider],
        metrics: MetricsCollector | None = None,
        retry: RetryPolicy | None = None,
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        if not providers:
            raise ValueError("ProviderRouter requires at least one provider")
        self._providers = providers
        self._metrics = metrics or default_metrics
        self._retry = retry or RetryPolicy()
        self._limiters = {p.name: RateLimiter(rate_per_sec, burst) for p in providers}

    @property
    def chain(self) -> list[str]:
        return [p.name for p in self._providers]

    def _run(
        self,
        op: str,
        exchange: Exchange | None,
        timeframe: Timeframe | None,
        call: Callable[[MarketDataProvider], T],
    ) -> T:
        last_exc: ProviderError | None = None
        for provider in self._providers:
            if exchange and timeframe and not provider.can_serve(exchange, timeframe):
                continue

            def _attempt(_p: MarketDataProvider = provider) -> T:
                if not self._limiters[_p.name].acquire():
                    self._metrics.incr("rate_limit_events", provider=_p.name)
                    raise ProviderRateLimitError(f"{_p.name} local rate limit exceeded")
                return call(_p)

            def _on_attempt(
                attempt: int,
                err: Exception | None,
                _p: MarketDataProvider = provider,
            ) -> None:
                if attempt > 1:
                    self._metrics.incr("retry_count", provider=_p.name, op=op)
                if err is not None:
                    self._metrics.incr("failed_requests", provider=_p.name, op=op)

            try:
                with self._metrics.timed("provider_latency", provider=provider.name, op=op):
                    result = with_retry(
                        _attempt, policy=self._retry, on_attempt=_on_attempt
                    )
                self._metrics.incr("requests", provider=provider.name, op=op)
                self._metrics.gauge("provider_available", 1.0, provider=provider.name)
                return result
            except ProviderError as exc:
                last_exc = exc
                self._metrics.gauge("provider_available", 0.0, provider=provider.name)
                log.warning("provider_failover", provider=provider.name, op=op, error=str(exc))
                continue
        raise last_exc or ProviderError(f"no provider could serve {op}")

    # --- MarketDataProvider surface (with failover) ---------------------
    def fetch_instruments(self, exchange: Exchange) -> list[InstrumentDTO]:
        return self._run("fetch_instruments", None, None, lambda p: p.fetch_instruments(exchange))

    def fetch_ohlcv(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe, start: date, end: date,
        asset_class: AssetClass | None = None,
    ) -> OHLCVResponse:
        return self._run(
            "fetch_ohlcv", exchange, timeframe,
            lambda p: p.fetch_ohlcv(symbol, exchange, timeframe, start, end, asset_class),
        )

    def fetch_corporate_actions(
        self, symbol: str, exchange: Exchange
    ) -> list[CorporateActionDTO]:
        return self._run(
            "fetch_corporate_actions", None, None,
            lambda p: p.fetch_corporate_actions(symbol, exchange),
        )

    def health_check(self) -> ProviderHealth:
        # Router health = health of the first provider that answers.
        for provider in self._providers:
            try:
                return provider.health_check()
            except ProviderError:
                continue
        return ProviderHealth(
            provider=self.name, status=ProviderStatus.down,
            detail="all providers unavailable", checked_at=_now(),
        )

    def health_all(self) -> list[ProviderHealth]:
        results: list[ProviderHealth] = []
        for provider in self._providers:
            try:
                results.append(provider.health_check())
            except ProviderError as exc:
                results.append(ProviderHealth(
                    provider=provider.name, status=ProviderStatus.down,
                    detail=str(exc), checked_at=_now(),
                ))
        return results


def _now() -> datetime:
    return datetime.now(UTC)


def build_router(
    primary: str,
    fallbacks: list[str] | None = None,
    metrics: MetricsCollector | None = None,
) -> ProviderRouter:
    """Construct the failover chain from configuration (primary first)."""
    _register_builtin()
    names: list[str] = [primary, *(fallbacks or [])]
    seen: set[str] = set()
    providers: list[MarketDataProvider] = []
    for n in names:
        if n in seen or n not in _REGISTRY:
            continue
        seen.add(n)
        providers.append(build_provider(n))
    if not providers:
        raise KeyError(f"no valid providers among {names}")
    return ProviderRouter(providers, metrics=metrics)
