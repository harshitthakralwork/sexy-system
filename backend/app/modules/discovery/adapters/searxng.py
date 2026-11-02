from __future__ import annotations

import time
from typing import Any

import httpx

from app.modules.discovery.adapters.base import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_WORKING,
    AccessDeniedError,
    AdapterCapabilities,
    AdapterError,
    DiscoveredItem,
    DiscoveryQuery,
    HealthResult,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.shared.url_safety import validate_service_base_url

# Hard ceilings, independent of configuration. Each one exists because a query is
# assembled from operator (and later, UI) input, and an unbounded fan-out against
# a search proxy gets the *instance* blocked by upstream engines — which then
# degrades discovery for every future run, not just the abusive one.
MAX_PAGES_LIMIT = 10
MAX_KEYWORDS_PER_QUERY = 10
MAX_RESULTS_LIMIT = 500
MAX_QUERY_LENGTH = 300


class QueryTooBroadError(AdapterError):
    def __init__(self, message: str) -> None:
        super().__init__(message, classification="unsupported_query", retryable=False)


def _raise_for_source_response(response: httpx.Response) -> None:
    """Map an HTTP failure to an honest classification.

    Bot protection and auth walls are reported as access denial. Nothing here
    attempts to get around them — that is forbidden by PRD section 17, and a
    workaround would also make the result untrustworthy.
    """
    if response.status_code in (200, 204):
        return
    if response.status_code == 429:
        raise RateLimitedError("SearXNG rate-limited this client")
    if response.status_code in (401, 403):
        raise AccessDeniedError(
            f"SearXNG refused the request ({response.status_code}). "
            "The instance may have its limiter enabled for JSON requests."
        )
    if response.status_code == 400:
        raise UnsupportedQueryError("SearXNG rejected the query parameters")
    raise AdapterError(f"SearXNG returned HTTP {response.status_code}", classification="http_error")


class SearxngAdapter:
    """Search discovery through a self-hosted SearXNG instance.

    SearXNG returns search results, not businesses. Every item here is a page
    that mentioned something — the pipeline decides whether it describes a
    business, which is why this adapter never invents a name or category.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 20.0,
        max_pages: int = 3,
        results_per_page: int = 20,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        origin = validate_service_base_url(base_url, field="SearXNG base_url")
        self._base_url = origin
        self._timeout = timeout_seconds
        self._max_pages = min(max(1, max_pages), MAX_PAGES_LIMIT)
        self._results_per_page = min(max(1, results_per_page), 50)
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="searxng",
            name="SearXNG (self-hosted)",
            slug="searxng",
            category="search",
            supported_query_types=("keyword", "category", "site_text"),
            supported_filters=("country", "language", "time_range"),
            available_fields=("title", "url", "snippet", "engine"),
            geographic_coverage=(
                "Depends on the engines enabled in the instance. Returns web pages "
                "matching a query, not exhaustive business listings for an area."
            ),
            access_requirements=("A reachable SearXNG instance with the JSON format enabled",),
            rate_limit_notes=(
                "Upstream engines throttle aggressive instances. Keep to one page at a "
                "time and treat failures of this source as normal, not exceptional."
            ),
            terms_notes="Respect each upstream engine's terms; SearXNG proxies them.",
            max_results_per_query=None,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        base_url = str(config.get("base_url", self._base_url)).strip()
        validate_service_base_url(base_url, field="SearXNG base_url")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        # Redirects off: a redirecting instance could move the request to a host
        # the configuration was never approved for.
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _params(self, query: DiscoveryQuery, keyword: str | None, page: int) -> dict[str, str]:
        search_term = " ".join(part for part in (keyword, *query.keywords) if part).strip()
        if query.category:
            search_term = f"{search_term} {query.category}".strip()
        if query.location and query.location.place_name:
            search_term = f"{search_term} {query.location.place_name}".strip()
        if len(search_term) > MAX_QUERY_LENGTH:
            raise QueryTooBroadError(
                f"Search term is {len(search_term)} characters; the limit is {MAX_QUERY_LENGTH}"
            )

        params: dict[str, str] = {"q": search_term, "format": "json", "pageno": str(page)}
        if query.country:
            params["country"] = query.country.lower()[:8]
        if query.extra.get("time_range"):
            params["time_range"] = str(query.extra["time_range"])[:16]
        return params

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredItem]:
        if query.is_empty():
            raise UnsupportedQueryError("A search needs at least a keyword or a category")
        if len(query.keywords) > MAX_KEYWORDS_PER_QUERY:
            raise QueryTooBroadError(
                f"At most {MAX_KEYWORDS_PER_QUERY} keywords per query; each one multiplies "
                "the request count by the number of pages"
            )
        if query.max_results > MAX_RESULTS_LIMIT:
            raise QueryTooBroadError(f"max_results is capped at {MAX_RESULTS_LIMIT}")

        client = await self._get_client()
        terms = query.keywords or ("",)
        collected: list[DiscoveredItem] = []
        seen_urls: set[str] = set()

        for term in terms:
            for page in range(1, self._max_pages + 1):
                response = await client.get(
                    f"{self._base_url}/search", params=self._params(query, term, page)
                )
                self.requests_made += 1
                _raise_for_source_response(response)

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise MalformedResponseError(
                        "SearXNG replied with a non-JSON body. "
                        "The instance likely has the JSON format disabled."
                    ) from exc

                if not isinstance(payload, dict):
                    raise MalformedResponseError("SearXNG response was not an object")

                results = payload.get("results")
                if results is None:
                    raise MalformedResponseError(
                        "SearXNG response had no results field: "
                        f"{str(payload.get('error', payload))[:200]}"
                    )

                fresh: list[DiscoveredItem] = []
                for item in self._to_items(results):
                    key = item.source_url
                    if key is None:
                        # Keep it. Deciding whether a URL-less hit is usable is the
                        # validation stage's job, not the adapter's.
                        fresh.append(item)
                    elif key not in seen_urls:
                        seen_urls.add(key)
                        fresh.append(item)
                collected.extend(fresh)

                if len(results) < self._results_per_page:
                    break
                if len(collected) >= query.max_results:
                    return collected[: query.max_results]

            if len(collected) >= query.max_results:
                break

        return collected[: query.max_results]

    def _to_items(self, results: list[dict[str, Any]]) -> list[DiscoveredItem]:
        items: list[DiscoveredItem] = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            items.append(
                DiscoveredItem(
                    external_id=str(entry.get("id")) if entry.get("id") is not None else None,
                    source_url=entry.get("url"),
                    title_hint=entry.get("title"),
                    # A search result's URL is a claim about the business's own
                    # site, which is why it goes in `website_hint` and not merely
                    # into provenance: it is the strongest identity signal a
                    # keyword hit carries. Provenance still records it as a
                    # search-result URL, never as a verified website.
                    website_hint=entry.get("url"),
                    raw_data=entry,
                )
            )
        return items

    async def health_check(self) -> HealthResult:
        """Prove the instance answers *and* serves JSON.

        An instance that returns HTML for a JSON request is not healthy for our
        purposes even though it is up for a human browser.
        """
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self._base_url}/search",
                params={"q": "healthcheck", "format": "json", "pageno": "1"},
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            _raise_for_source_response(response)
            try:
                payload = response.json()
            except ValueError:
                # Up and serving HTML is not healthy for a JSON consumer, and
                # "degraded" tells the operator to enable the format rather
                # than implying the instance is down.
                return HealthResult(
                    status=HEALTH_DEGRADED,
                    detail="Responding, but not returning JSON results",
                    response_time_ms=elapsed,
                )
            if not isinstance(payload, dict) or "results" not in payload:
                return HealthResult(
                    status=HEALTH_DEGRADED,
                    detail="Responding, but not returning JSON results",
                    response_time_ms=elapsed,
                )
            return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except httpx.HTTPError as exc:
            # Type name only: httpx error text can contain the request URL.
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - a health probe reports, never raises
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
