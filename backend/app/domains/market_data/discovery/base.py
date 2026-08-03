"""Discovery source contract + the shared HTTP client used by exchange feeds.

Exchange endpoints are not friendly APIs: they reject non-browser user agents,
require a cookie handshake against the parent site, and serve CSVs in whatever
encoding the upstream system happened to write. That handling is centralised in
:class:`ExchangeHttpClient` so each source stays a thin parser.
"""
from __future__ import annotations

import csv
import http.cookiejar
import io
import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.domains.market_data.enums import AssetClass, Exchange
from app.domains.market_data.schemas import InstrumentDTO

log = get_logger(__name__)

#: Exchange sites reject the default urllib agent outright; a browser UA is the
#: minimum required to get a response at all.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

#: Tried in order; exchange CSVs are inconsistently encoded (NSE's ETF list is
#: cp1252 while its equity list is UTF-8), so decoding must never hard-fail.
_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


class DiscoveryError(Exception):
    """A discovery source could not produce a usable instrument list."""


def decode_text(raw: bytes) -> str:
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class ExchangeHttpClient:
    """Cookie-persisting HTTP client with browser headers and bounded retries."""

    def __init__(
        self,
        timeout: float = 45.0,
        max_attempts: int = 3,
        backoff: float = 1.5,
        user_agent: str = BROWSER_UA,
    ) -> None:
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff = backoff
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self._opener.addheaders = [
            ("User-Agent", user_agent),
            ("Accept", "text/html,application/xhtml+xml,application/json,text/csv,*/*"),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Connection", "keep-alive"),
        ]

    def get_bytes(self, url: str, referer: str | None = None) -> bytes:
        last: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            request = urllib.request.Request(url)
            if referer:
                request.add_header("Referer", referer)
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return bytes(response.read())
            except (urllib.error.URLError, OSError) as exc:
                last = exc
                if attempt == self._max_attempts:
                    break
                delay = self._backoff ** attempt
                log.warning(
                    "discovery_http_retry", url=url, attempt=attempt,
                    delay=round(delay, 2), error=str(exc),
                )
                time.sleep(delay)
        raise DiscoveryError(f"GET {url} failed after {self._max_attempts} attempts: {last}")

    def get_csv(self, url: str, referer: str | None = None) -> list[dict[str, str]]:
        text = decode_text(self.get_bytes(url, referer=referer))
        reader = csv.DictReader(io.StringIO(text))
        # Exchange CSV headers carry stray spaces (" SERIES", " ISIN NUMBER").
        return [
            {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in reader
        ]

    def get_json(self, url: str, referer: str | None = None) -> Any:
        raw = self.get_bytes(url, referer=referer)
        try:
            return json.loads(decode_text(raw))
        except ValueError as exc:
            raise DiscoveryError(f"GET {url} returned non-JSON payload") from exc

    def warm(self, url: str) -> None:
        """Best-effort cookie handshake. Some endpoints only work post-handshake,
        and some parent pages 403 the request while still setting usable cookies —
        so a failure here is never fatal."""
        try:
            self.get_bytes(url)
        except DiscoveryError as exc:
            log.debug("discovery_warm_failed", url=url, error=str(exc))


@dataclass
class SourceResult:
    """One source's output plus everything the report needs to explain it."""

    source: str
    exchange: Exchange
    asset_class: AssetClass
    instruments: list[InstrumentDTO] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def count(self) -> int:
        return len(self.instruments)


class InstrumentSource(ABC):
    """Authority for one (exchange, asset class) slice of the tradable universe.

    Adding an asset class — futures, mutual funds, US equities, crypto — means
    adding a source and registering it. No other layer changes, which is the
    whole point of keeping discovery separate from price providers.
    """

    #: Stable identifier used in config, provenance, and reporting.
    name: str = "base"
    exchange: Exchange
    asset_class: AssetClass = AssetClass.equity

    def __init__(self, client: ExchangeHttpClient | None = None) -> None:
        self._client = client or ExchangeHttpClient()

    @abstractmethod
    def fetch(self) -> list[InstrumentDTO]:
        """Return every instrument in this slice, including inactive ones.

        Sources must report lifecycle honestly via ``is_active`` / ``is_delisted``
        rather than silently omitting retired instruments — reconciliation needs
        to distinguish "delisted" from "the feed broke".
        """

    def collect(self) -> SourceResult:
        """Run :meth:`fetch` and wrap the outcome. Never raises.

        One broken feed must not abort discovery of the rest of the market, so
        failures are captured into the result and surfaced in the report.
        """
        started = time.perf_counter()
        try:
            instruments = self.fetch()
        except Exception as exc:  # noqa: BLE001 - isolate one source's failure
            log.warning("discovery_source_failed", source=self.name, error=str(exc))
            return SourceResult(
                source=self.name, exchange=self.exchange, asset_class=self.asset_class,
                ok=False, error=f"{type(exc).__name__}: {exc}",
                duration_seconds=round(time.perf_counter() - started, 3),
            )
        result = SourceResult(
            source=self.name, exchange=self.exchange, asset_class=self.asset_class,
            instruments=instruments,
            duration_seconds=round(time.perf_counter() - started, 3),
        )
        log.info("discovery_source_ok", source=self.name, count=result.count,
                 seconds=result.duration_seconds)
        return result
