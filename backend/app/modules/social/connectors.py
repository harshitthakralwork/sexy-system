"""Social & Demand Intelligence Engine — keyless source connectors (Phase 2).

Every connector here satisfies the existing ``SocialAdapter`` contract and adds no
credential dependency, so it can run today. Capability claims are stated as they
truly are: Hacker News answers about HN; RSS returns whatever a feed publishes;
SearXNG surfaces *indexed snippets* whose coverage depends on upstream search
engines, not an independent index of the internet. None of them is allowed to look
like more than it is.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

import httpx

from app.modules.discovery.adapters.base import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_UNKNOWN,
    HEALTH_WORKING,
    AccessDeniedError,
    AdapterCapabilities,
    AdapterError,
    HealthResult,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.modules.social.adapters import SocialResult
from app.shared.normalization import canonical_hash, sanitize_text
from app.shared.url_safety import (
    UnsafeUrlError,
    validate_discovered_target,
    validate_service_base_url,
)

MAX_RESULTS_LIMIT = 100
MAX_QUERY_LENGTH = 300
MAX_FEED_BYTES = 2_000_000  # 2 MB per feed; a larger body is refused, not parsed.


def _iso(dt_epoch: Any) -> datetime | None:
    if isinstance(dt_epoch, (int, float)):
        return datetime.fromtimestamp(dt_epoch, tz=UTC)
    return None


def _raise_for_response(source: str, response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    if response.status_code == 429:
        raise RateLimitedError(f"{source} rate-limited this client (HTTP 429)")
    if response.status_code in (401, 403):
        raise AccessDeniedError(
            f"{source} refused the request ({response.status_code}). Public access may "
            "be blocked for this client."
        )
    if response.status_code == 400:
        raise UnsupportedQueryError(f"{source} rejected the query parameters")
    raise AdapterError(
        f"{source} returned HTTP {response.status_code}", classification="http_error"
    )


def _bounded_user_agent(user_agent: str, source: str) -> str:
    if not user_agent.strip():
        raise AdapterError(
            f"A descriptive User-Agent is required for {source}", classification="misconfigured"
        )
    return user_agent.strip()


class HackerNewsAdapter:
    """Hacker News via the Algolia public search API — no key, no login.

    Surfaces stories, Ask HN / Show HN posts and comments, which are exactly the
    technology- and startup-adjacent signals the Business track wants. It cannot
    see anything off HN, and says so.
    """

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        site: str = "https://news.ycombinator.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = validate_service_base_url(base_url, field="Hacker News base_url")
        self._site = validate_service_base_url(site, field="Hacker News site")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="hackernews",
            name="Hacker News (Algolia public search)",
            slug="hackernews",
            category="social",
            supported_query_types=("keyword", "author", "front_page"),
            supported_filters=("date_range", "tags"),
            available_fields=(
                "title",
                "text",
                "url",
                "author",
                "created_at",
                "points",
                "num_comments",
            ),
            geographic_coverage="Global; Hacker News discussion is predominantly English.",
            access_requirements=("None — the Algolia HN search API is public and key-free",),
            rate_limit_notes="Subject to Algolia's public rate limits; one request per run.",
            terms_notes="Public HN content via the official Algolia search index.",
            max_results_per_query=MAX_RESULTS_LIMIT,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        self._validate(config)

    def _validate(self, config: dict[str, Any]) -> None:
        kind = str(config.get("kind", "search"))
        if kind not in ("search", "ask_hn", "show_hn", "front_page", "user"):
            raise UnsupportedQueryError(f"Unsupported Hacker News query kind: {kind}")
        q = str(config.get("q", "")).strip()
        if kind in ("search", "user") and kind == "search" and not q:
            raise UnsupportedQueryError("A Hacker News keyword search needs a non-empty 'q'")
        if kind == "user" and not str(config.get("author", "")).strip():
            raise UnsupportedQueryError("A Hacker News user query needs an 'author'")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; the limit is {MAX_QUERY_LENGTH}")
        limit = int(config.get("limit", 25))
        if not 1 <= limit <= MAX_RESULTS_LIMIT:
            raise UnsupportedQueryError(f"limit must be between 1 and {MAX_RESULTS_LIMIT}")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": _bounded_user_agent(self._user_agent, "Hacker News")},
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _path_and_params(self, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        kind = str(config.get("kind", "search"))
        limit = int(config.get("limit", 25))
        params: dict[str, Any] = {"hitsPerPage": limit}
        q = str(config.get("q", "")).strip()
        if q:
            params["query"] = q
        date_after = config.get("date_after")
        if isinstance(date_after, (int, float)):
            params["numericFilters"] = f"created_at_i>{int(date_after)}"
        if kind == "ask_hn":
            params["tags"] = "ask_hn"
            return "/api/v1/search", params
        if kind == "show_hn":
            params["tags"] = "show_hn"
            return "/api/v1/search", params
        if kind == "front_page":
            params["tags"] = "front_page"
            return "/api/v1/search", params
        if kind == "user":
            params["tags"] = f"author_{str(config['author']).strip()}"
            return "/api/v1/search_by_date", params
        return "/api/v1/search", params

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        self._validate(config)
        client = await self._get_client()
        path, params = self._path_and_params(config)
        response = await client.get(f"{self._base_url}{path}", params=params)
        self.requests_made += 1
        _raise_for_response("Hacker News", response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError("Hacker News replied with a non-JSON body") from exc
        return self._to_results(payload)

    def _to_results(self, payload: Any) -> list[SocialResult]:
        if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
            raise MalformedResponseError("Hacker News response had no 'hits' array")
        results: list[SocialResult] = []
        for hit in payload["hits"]:
            if not isinstance(hit, dict):
                continue
            object_id = hit.get("objectID")
            if not object_id:
                continue
            tags = hit.get("tags") or []
            is_comment = "comment" in tags
            item_url = hit.get("url")
            story_url = hit.get("story_url")
            permalink = f"{self._site}/item?id={object_id}"
            content_url = item_url or story_url or permalink
            title = sanitize_text(hit.get("title")) or sanitize_text(hit.get("story_title"))
            text = sanitize_text(hit.get("text"))
            content_text = "\n\n".join(part for part in (title, text) if part) or None
            created = hit.get("created_at_i")
            author = hit.get("author")
            author_name = author if isinstance(author, str) and author.strip() else None
            results.append(
                SocialResult(
                    external_id=str(object_id),
                    content_url=content_url if isinstance(content_url, str) else permalink,
                    content_type="comment" if is_comment else "post",
                    content_text=content_text,
                    published_at=_iso(created),
                    engagement={
                        "points": hit.get("points"),
                        "num_comments": hit.get("num_comments"),
                        "tags": tags,
                    },
                    author_external_id=author_name,
                    author_username=author_name,
                    raw_data=hit,
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self._base_url}/api/v1/search", params={"hitsPerPage": "1"}
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            _raise_for_response("Hacker News", response)
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("hits"), list):
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            return HealthResult(HEALTH_DEGRADED, "Responding, but not a known shape", elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except httpx.HTTPError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - a health probe reports, never raises
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)


class RssAtomAdapter:
    """Configurable public RSS / Atom feeds, parsed with the standard library.

    A feed is only as good as what its publisher puts in it: some carry full text,
    most carry a snippet. The adapter never pretends a snippet is a retrieved body,
    refuses anything but http(s), and applies the same SSRF guard as discovery so a
    user-supplied feed URL cannot reach private or metadata endpoints.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        max_entries_per_feed: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._max_entries = max_entries_per_feed
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="rss",
            name="RSS / Atom (public feeds)",
            slug="rss",
            category="social",
            supported_query_types=("feed_url",),
            supported_filters=("date_range",),
            available_fields=("title", "link", "description", "published"),
            geographic_coverage="Depends entirely on the feed the user configures.",
            access_requirements=("None — public feeds only",),
            rate_limit_notes="One HTTP request per configured feed per run.",
            terms_notes="Content retrieval is limited to what the feed itself publishes.",
            max_results_per_query=self._max_entries,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        feeds = config.get("feed_urls")
        if not isinstance(feeds, list) or not feeds:
            raise UnsupportedQueryError("An RSS query needs a non-empty 'feed_urls' list")
        if len(feeds) > 20:
            raise UnsupportedQueryError("At most 20 feed URLs per run")
        for raw in feeds:
            self._safe_feed_url(str(raw))

    @staticmethod
    def _safe_feed_url(raw: str) -> str:
        parts = urlsplit(raw.strip())
        if parts.scheme not in ("http", "https"):
            raise UnsupportedQueryError("Feed URLs must be http(s)")
        # Refuse private / metadata / non-resolvable targets — same guard as discovery,
        # surfaced as a query rejection so a bad feed URL is a clean error, not a 500.
        try:
            validate_discovered_target(raw.strip())
        except UnsafeUrlError as exc:
            raise UnsupportedQueryError(f"Feed URL is not allowed by SSRF policy: {exc}") from exc
        return raw.strip()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": _bounded_user_agent(self._user_agent, "RSS feeds")},
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        client = await self._get_client()
        collected: list[SocialResult] = []
        errors: list[str] = []
        for raw in config["feed_urls"]:
            url = str(raw).strip()
            try:
                response = await client.get(url)
                self.requests_made += 1
                _raise_for_response("Feed", response)
                if len(response.content) > MAX_FEED_BYTES:
                    raise MalformedResponseError("Feed body exceeded the size limit")
                collected.extend(self._parse(response.text, url))
            except (AccessDeniedError, RateLimitedError) as exc:
                errors.append(f"{url}: {exc.message}")
            except (httpx.HTTPError, MalformedResponseError) as exc:
                errors.append(f"{url}: {type(exc).__name__}")
        if errors and not collected:
            raise AdapterError(
                "No feed could be fetched: " + "; ".join(errors), classification="source_error"
            )
        return collected

    def _parse(self, text: str, feed_url: str) -> list[SocialResult]:
        # Refuse DTDs outright: this is untrusted XML and ElementTree does not stop
        # entity-expansion attacks on its own.
        if "<!DOCTYPE" in text[:2048].upper():
            raise MalformedResponseError("Feed declared a DTD; refusing to parse")
        try:
            root = ET.fromstring(text)
        except ParseError as exc:
            raise MalformedResponseError("Feed was not well-formed XML") from exc

        results: list[SocialResult] = []
        ns_atom = "{http://www.w3.org/2005/Atom}"
        entries = root.findall("./channel/item") or root.findall(f".//{ns_atom}entry")
        for entry in entries[: self._max_entries]:
            results.append(self._entry_to_result(entry, feed_url, ns_atom))
        return results

    def _entry_to_result(self, entry: Any, feed_url: str, ns_atom: str) -> SocialResult:
        title = self._text(entry, "title") or self._text(entry, f"{ns_atom}title")
        link = (
            self._text(entry, "link")
            or self._text(entry, "guid")
            or self._text(entry, f"{ns_atom}link")
        )
        if link is None:
            atom_link = entry.find(f"{ns_atom}link")
            if atom_link is not None:
                link = atom_link.get("href")
        description = (
            self._text(entry, "description")
            or self._text(entry, "summary")
            or self._text(entry, f"{ns_atom}summary")
            or self._text(entry, "content")
            or self._text(entry, f"{ns_atom}content")
        )
        published = (
            self._text(entry, "pubDate")
            or self._text(entry, "published")
            or self._text(entry, f"{ns_atom}published")
            or self._text(entry, "updated")
            or self._text(entry, f"{ns_atom}updated")
        )
        author = (
            self._text(entry, "author")
            or self._text(entry, "dc:creator")
            or self._text(entry, f"{ns_atom}author/{ns_atom}name")
        )
        stable = link or f"{feed_url}::{title}"
        external_id = canonical_hash(stable)
        return SocialResult(
            external_id=external_id,
            content_url=link,
            content_type="post",
            content_text="\n\n".join(part for part in (title, description) if part) or None,
            published_at=self._parse_date(published),
            engagement={"feed_url": feed_url, "has_full_content": bool(description)},
            author_display_name=author,
            raw_data={"feed_url": feed_url, "title": title, "link": link, "published": published},
        )

    @staticmethod
    def _text(entry: Any, tag: str) -> str | None:
        found = entry.find(tag)
        if found is not None and found.text:
            return found.text.strip()
        return None

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        cleaned = value.strip()
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    async def health_check(self) -> HealthResult:
        # A feed's health is only meaningful against a specific URL, and search()
        # probes those; a config-less global probe would be a lie.
        return HealthResult(
            status=HEALTH_UNKNOWN, detail="Health is per-feed; run a track to check one."
        )


class SearxngSocialAdapter:
    """Publicly indexed social content found through a self-hosted SearXNG.

    SearXNG is a metasearch layer over other engines — it does not hold its own
    index of the internet, and every result here is an *indexed snippet*, never a
    confirmed retrieval of the underlying post. That distinction is stamped onto
    the record so the pipeline can label it honestly. It is the permitted path to
    LinkedIn/Instagram/X snippets: public search results only, never login
    automation or cookie scraping.
    """

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        results_per_page: int = 20,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = validate_service_base_url(base_url, field="SearXNG base_url")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._results_per_page = results_per_page
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="searxng",
            name="Web index via self-hosted SearXNG (snippets only)",
            slug="searxng",
            category="social",
            supported_query_types=("keyword", "site"),
            supported_filters=("language", "time_range"),
            available_fields=("title", "url", "snippet", "publishedDate"),
            geographic_coverage="Depends on the upstream engines a query hits.",
            access_requirements=("A reachable SearXNG instance (SPARKX_SEARXNG_BASE_URL)",),
            rate_limit_notes="Inherits the limits of the upstream engines it aggregates.",
            terms_notes=(
                "Results are search-index snippets, not retrieved posts. Coverage is "
                "not guaranteed and is never represented as complete."
            ),
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(config.get("q", "")).strip()
        if not q:
            raise UnsupportedQueryError("A SearXNG social query needs a non-empty 'q'")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; the limit is {MAX_QUERY_LENGTH}")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": _bounded_user_agent(self._user_agent, "SearXNG")},
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        client = await self._get_client()
        params: dict[str, Any] = {
            "q": str(config["q"]).strip(),
            "format": "json",
            "pageno": int(config.get("pageno", 1)),
        }
        if config.get("language"):
            params["language"] = str(config["language"])
        if config.get("time_range"):
            params["time_range"] = str(config["time_range"])
        if config.get("categories"):
            params["categories"] = str(config["categories"])
        response = await client.get(f"{self._base_url}/search", params=params)
        self.requests_made += 1
        _raise_for_response("SearXNG", response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError("SearXNG replied with a non-JSON body") from exc
        return self._to_results(payload)

    def _to_results(self, payload: Any) -> list[SocialResult]:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise MalformedResponseError("SearXNG response had no 'results' array")
        results: list[SocialResult] = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            title = sanitize_text(item.get("title"))
            snippet = sanitize_text(item.get("content"))
            results.append(
                SocialResult(
                    external_id=canonical_hash(url.strip()),
                    content_url=url.strip(),
                    content_type="other",
                    content_text="\n\n".join(part for part in (title, snippet) if part) or None,
                    published_at=None,
                    engagement={"engine": item.get("engine"), "position": item.get("position")},
                    raw_data={**item, "retrieval_hint": "indexed_snippet"},
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self._base_url}/search", params={"q": "test", "format": "json"}
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            _raise_for_response("SearXNG", response)
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("results"), list):
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            return HealthResult(HEALTH_DEGRADED, "Responding, but no results array", elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except httpx.HTTPError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - a health probe reports, never raises
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)


ADAPTER_REGISTRY: dict[str, str] = {
    "reddit": "RedditAdapter",
    "hackernews": "HackerNewsAdapter",
    "rss": "RssAtomAdapter",
    "searxng": "SearxngSocialAdapter",
}
