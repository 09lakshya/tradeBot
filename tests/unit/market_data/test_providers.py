"""Provider interface conformance, failover, and config-driven switching."""
from datetime import date

import pytest

from app.domains.market_data.enums import Exchange, ProviderStatus, Timeframe
from app.domains.market_data.providers.base import (
    MarketDataProvider,
    ProviderError,
    ProviderTimeoutError,
)
from app.domains.market_data.providers.mock import MockProvider
from app.domains.market_data.providers.registry import (
    ProviderRouter,
    available_providers,
    build_router,
)
from app.domains.market_data.providers.resilience import RetryPolicy

START, END = date(2026, 1, 1), date(2026, 1, 10)


def test_mock_provider_conforms_to_interface() -> None:
    provider = MockProvider()
    assert isinstance(provider, MarketDataProvider)
    for method in ("fetch_instruments", "fetch_ohlcv",
                   "fetch_corporate_actions", "health_check"):
        assert callable(getattr(provider, method))


def test_mock_ohlcv_is_deterministic() -> None:
    a = MockProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    b = MockProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    assert [x.close for x in a.bars] == [x.close for x in b.bars]
    assert a.bars, "provider must return bars"


def test_mock_bars_are_internally_consistent() -> None:
    resp = MockProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    for b in resp.bars:
        assert b.high >= max(b.open, b.close)
        assert b.low <= min(b.open, b.close)
        assert b.volume >= 0
        assert b.ts.tzinfo is not None


def test_can_serve_filters_exchange_and_timeframe() -> None:
    provider = MockProvider()
    assert provider.can_serve(Exchange.NSE, Timeframe.d1)


def test_router_fails_over_to_healthy_provider() -> None:
    broken = MockProvider(fail_first=99)          # always fails
    healthy = MockProvider(seed=7)
    router = ProviderRouter([broken, healthy], retry=RetryPolicy(max_attempts=1, base_delay=0.01))
    resp = router.fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    assert resp.bars, "failover must produce data from the healthy provider"


def test_router_raises_when_all_providers_fail() -> None:
    router = ProviderRouter(
        [MockProvider(fail_first=99), MockProvider(fail_first=99)],
        retry=RetryPolicy(max_attempts=1, base_delay=0.01),
    )
    with pytest.raises(ProviderError):
        router.fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)


def test_router_retries_before_failing_over() -> None:
    # Fails twice then succeeds — retry should rescue it without failover.
    flaky = MockProvider(fail_first=2, fail_kind="timeout")
    router = ProviderRouter([flaky], retry=RetryPolicy(max_attempts=3, base_delay=0.01))
    resp = router.fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)
    assert resp.bars


def test_router_surfaces_rate_limit_as_transient() -> None:
    flaky = MockProvider(fail_first=1, fail_kind="rate_limit")
    router = ProviderRouter([flaky], retry=RetryPolicy(max_attempts=2, base_delay=0.01))
    assert router.fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END).bars


def test_router_chain_reports_order() -> None:
    router = ProviderRouter([MockProvider(), MockProvider()])
    assert router.chain == ["mock", "mock"]


def test_router_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ProviderRouter([])


def test_health_all_reports_every_provider() -> None:
    router = ProviderRouter([MockProvider(), MockProvider()])
    health = router.health_all()
    assert len(health) == 2
    assert all(h.status is ProviderStatus.up for h in health)


def test_build_router_from_config_names() -> None:
    router = build_router(primary="mock")
    assert "mock" in router.chain


def test_build_router_rejects_unknown_primary() -> None:
    with pytest.raises(KeyError):
        build_router(primary="does_not_exist")


def test_registry_lists_builtin_providers() -> None:
    build_router(primary="mock")   # triggers builtin registration
    names = available_providers()
    for expected in ("yahoo", "mock", "alpha_vantage", "twelve_data", "finnhub"):
        assert expected in names


def test_unconfigured_stub_provider_reports_down() -> None:
    from app.domains.market_data.providers.finnhub import FinnhubProvider

    health = FinnhubProvider().health_check()
    assert health.status is ProviderStatus.down
    assert "not configured" in (health.detail or "")


def test_stub_provider_raises_rather_than_returning_wrong_data() -> None:
    from app.domains.market_data.providers.twelve_data import TwelveDataProvider

    with pytest.raises(ProviderError):
        TwelveDataProvider().fetch_ohlcv("TCS", Exchange.NSE, Timeframe.d1, START, END)


def test_mock_failure_injection_kinds() -> None:
    with pytest.raises(ProviderTimeoutError):
        MockProvider(fail_first=1, fail_kind="timeout").fetch_instruments(Exchange.NSE)
