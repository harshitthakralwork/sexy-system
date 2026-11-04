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
        try:
            response = await client.get(f"{self._base_url}/search", params=params)
            self.requests_made += 1
            _raise_for_response("SearXNG", response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise MalformedResponseError("SearXNG replied with a non-JSON body") from exc
            return self._to_results(payload)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return await self._fallback_social_search(config)

    async def _fallback_social_search(self, config: dict[str, Any]) -> list[SocialResult]:
        import html
        import re
        import urllib.parse

        q = str(config["q"]).strip()
        client = await self._get_client()
        try:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": q},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return []
            raw_text = resp.text
            matches = re.findall(
                r'<a class="result__snippet[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                raw_text,
                re.DOTALL,
            )
            titles = re.findall(
                r'<h2 class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                raw_text,
                re.DOTALL,
            )
            title_map: dict[str, str] = {}
            for u, t in titles:
                parsed_u = (
                    urllib.parse.unquote(u.split("uddg=")[-1].split("&")[0])
                    if "uddg=" in u
                    else u
                )
                clean_t = html.unescape(re.sub(r"<[^>]+>", "", t).strip())
                title_map[parsed_u] = clean_t

            results: list[SocialResult] = []
            seen: set[str] = set()
            for raw_u, s in matches:
                u = (
                    urllib.parse.unquote(raw_u.split("uddg=")[-1].split("&")[0])
                    if "uddg=" in raw_u
                    else raw_u
                )
                if not u.startswith("http") or u in seen:
                    continue
                seen.add(u)
                snippet = html.unescape(re.sub(r"<[^>]+>", "", s).strip())
                title = title_map.get(u) or u
                full_text = f"{title}\n\n{snippet}" if snippet else title
                results.append(
                    SocialResult(
                        external_id=canonical_hash(u.strip()),
                        content_url=u.strip(),
                        content_type="post",
                        content_text=full_text,
                        published_at=None,
                        engagement={"engine": "duckduckgo_fallback"},
                        raw_data={"url": u, "title": title, "snippet": snippet, "retrieval_hint": "web_dorking"},
                    )
                )
            return results
        except Exception:
            return []

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


def _parse_iso_str(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class _HttpConnector:
    """Shared plumbing for JSON connectors: a bounded client and error mapping."""

    source_name = "source"

    def __init__(
        self,
        base_url: str,
        *,
        endpoint: str,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = validate_service_base_url(base_url, field=f"{self.source_name} base_url")
        self._endpoint = endpoint
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": _bounded_user_agent(self._user_agent, self.source_name)},
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        client = await self._get_client()
        response = await client.get(f"{self._base_url}{path}", params=params)
        self.requests_made += 1
        _raise_for_response(self.source_name, response)
        try:
            return response.json()
        except ValueError as exc:
            raise MalformedResponseError(
                f"{self.source_name} replied with a non-JSON body"
            ) from exc


class StackOverflowAdapter(_HttpConnector):
    """Stack Overflow questions via the public API — no key for low volume.

    The API is anonymous-friendly but hard rate-limited without a key, and answers
    only about Stack Overflow; that is stated in capabilities, not hidden.
    """

    source_name = "Stack Overflow"

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url,
            endpoint="/2.3/search/advanced",
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="stackoverflow",
            name="Stack Overflow (public API)",
            slug="stackoverflow",
            category="social",
            supported_query_types=("keyword",),
            supported_filters=("sort", "tag"),
            available_fields=("title", "link", "score", "answer_count", "creation_date", "tags"),
            geographic_coverage="Global; English-language developer Q&A.",
            access_requirements=("None for low volume; a key raises the rate limit",),
            rate_limit_notes="Anonymous access is rate-limited (~300 req/day) by Stack Exchange.",
            terms_notes="Public questions only, via the official API.",
            max_results_per_query=50,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        if not str(config.get("q", "")).strip():
            raise UnsupportedQueryError("Stack Overflow needs a non-empty 'q'")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        sort = str(config.get("sort", "creation")).lower()
        # Older saved queries used Reddit's "new" value. Keep them runnable.
        if sort == "new":
            sort = "creation"
        if sort not in {"activity", "votes", "creation", "relevance"}:
            raise UnsupportedQueryError(
                "Stack Overflow sort must be activity, votes, creation, or relevance"
            )
        params = {
            "order": "desc",
            "sort": sort,
            "q": str(config["q"]).strip(),
            "site": "stackoverflow",
            "pagesize": min(int(config.get("limit", 25)), 50),
        }
        if config.get("tagged"):
            params["tagged"] = str(config["tagged"])
        payload = await self._get_json("/2.3/search/advanced", params)
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise MalformedResponseError("Stack Overflow response had no 'items' array")
        results: list[SocialResult] = []
        for q in items:
            if not isinstance(q, dict) or q.get("question_id") is None:
                continue
            title = sanitize_text(q.get("title"))
            body = sanitize_text(q.get("body"))
            results.append(
                SocialResult(
                    external_id=str(q["question_id"]),
                    content_url=q.get("link"),
                    content_type="post",
                    content_text="\n\n".join(part for part in (title, body) if part) or None,
                    published_at=_iso(q.get("creation_date")),
                    engagement={
                        "score": q.get("score"),
                        "answer_count": q.get("answer_count"),
                        "tags": q.get("tags"),
                    },
                    raw_data=q,
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        try:
            payload = await self._get_json("/2.3/info", {"site": "stackoverflow"})
            elapsed = int((time.perf_counter() - started) * 1000)
            if isinstance(payload, dict) and "items" in payload:
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            return HealthResult(HEALTH_DEGRADED, "Responding, but not a known shape", elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except (httpx.HTTPError, MalformedResponseError, AdapterError) as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)


class BlueskyAdapter(_HttpConnector):
    """Bluesky public posts via the unauthenticated app.bsky search endpoint.

    Only public posts are returned; the endpoint returns author handles, not private
    data, and coverage is limited to what Bluesky's public search indexes.
    """

    source_name = "Bluesky"

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url,
            endpoint="/xrpc/app.bsky.feed.searchPosts",
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="bluesky",
            name="Bluesky (public search)",
            slug="bluesky",
            category="social",
            supported_query_types=("keyword",),
            supported_filters=("sort",),
            available_fields=("text", "uri", "indexedAt", "author"),
            geographic_coverage="Global; public posts only.",
            access_requirements=("None — the public search endpoint is unauthenticated",),
            rate_limit_notes="Subject to Bluesky's public API limits.",
            terms_notes="Public posts only; author handles, never private content.",
            max_results_per_query=100,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        if not str(config.get("q", "")).strip():
            raise UnsupportedQueryError("Bluesky needs a non-empty 'q'")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        params = {
            "q": str(config["q"]).strip(),
            "limit": min(int(config.get("limit", 25)), 100),
            "sort": config.get("sort", "latest"),
        }
        payload = await self._get_json("/xrpc/app.bsky.feed.searchPosts", params)
        posts = payload.get("posts") if isinstance(payload, dict) else None
        if not isinstance(posts, list):
            raise MalformedResponseError("Bluesky response had no 'posts' array")
        results: list[SocialResult] = []
        for post in posts:
            if not isinstance(post, dict):
                continue
            record = post.get("record") or {}
            author = post.get("author") or {}
            handle = author.get("handle")
            rkey = str(post.get("uri", "")).rsplit("/", 1)[-1] or None
            url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else None
            text = sanitize_text(record.get("text"))
            results.append(
                SocialResult(
                    external_id=str(post.get("cid") or post.get("uri") or rkey or ""),
                    content_url=url,
                    content_type="post",
                    content_text=text,
                    published_at=_parse_iso_str(record.get("createdAt") or post.get("indexedAt")),
                    engagement={
                        "reposts": post.get("repostsCount"),
                        "likes": post.get("likesCount"),
                    },
                    author_external_id=handle,
                    author_username=handle,
                    author_display_name=author.get("displayName"),
                    author_profile_url=f"https://bsky.app/profile/{handle}" if handle else None,
                    raw_data=post,
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        try:
            payload = await self._get_json(
                "/xrpc/app.bsky.feed.searchPosts", {"q": "test", "limit": "1"}
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            if isinstance(payload, dict) and isinstance(payload.get("posts"), list):
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            return HealthResult(HEALTH_DEGRADED, "Responding, but no posts array", elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except (httpx.HTTPError, MalformedResponseError, AdapterError) as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)


class MastodonAdapter(_HttpConnector):
    """Mastodon statuses via a configurable instance's search endpoint.

    Unauthenticated search support varies by instance and version; when an instance
    refuses, this reports the refusal honestly rather than pretending coverage. The
    instance host is user/operator configured (default public instance).
    """

    source_name = "Mastodon"

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url,
            endpoint="/api/v2/search",
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="mastodon",
            name="Mastodon (instance search)",
            slug="mastodon",
            category="social",
            supported_query_types=("keyword",),
            supported_filters=("type",),
            available_fields=("content", "url", "created_at", "account"),
            geographic_coverage="Depends on the configured instance's visibility rules.",
            access_requirements=("Unauthenticated search availability varies by instance",),
            rate_limit_notes="Per-instance rate limits; a refused instance is reported as failed.",
            terms_notes="Public toots only; no login automation or private access.",
            max_results_per_query=40,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        if not str(config.get("q", "")).strip():
            raise UnsupportedQueryError("Mastodon needs a non-empty 'q'")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        params = {
            "q": str(config["q"]).strip(),
            "type": "statuses",
            "resolve": "false",
            "limit": min(int(config.get("limit", 20)), 40),
        }
        payload = await self._get_json("/api/v2/search", params)
        statuses = payload.get("statuses") if isinstance(payload, dict) else None
        if not isinstance(statuses, list):
            raise MalformedResponseError("Mastodon response had no 'statuses' array")
        results: list[SocialResult] = []
        for s in statuses:
            if not isinstance(s, dict) or s.get("id") is None:
                continue
            account = s.get("account") or {}
            results.append(
                SocialResult(
                    external_id=str(s["id"]),
                    content_url=s.get("url"),
                    content_type="post",
                    content_text=sanitize_text(s.get("content")),
                    published_at=_parse_iso_str(s.get("created_at")),
                    engagement={
                        "replies": s.get("replies_count"),
                        "favourites": s.get("favourites_count"),
                        "reblogs": s.get("reblogs_count"),
                    },
                    author_external_id=account.get("acct") or account.get("username"),
                    author_username=account.get("username"),
                    author_display_name=account.get("display_name"),
                    author_profile_url=account.get("url"),
                    raw_data=s,
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        try:
            payload = await self._get_json("/api/v2/instance", {})
            elapsed = int((time.perf_counter() - started) * 1000)
            if isinstance(payload, dict) and payload.get("domain"):
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            return HealthResult(HEALTH_DEGRADED, "Responding, but no instance domain", elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except (httpx.HTTPError, MalformedResponseError, AdapterError) as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)




class SearxngDorkingAdapter:
    """Base class for social intelligence querying via Google / SearXNG dorking."""

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        results_per_page: int = 20,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._searxng = SearxngSocialAdapter(
            base_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            results_per_page=results_per_page,
            client=client,
        )
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._results_per_page = results_per_page
        self._client = client
        self.requests_made = 0

    async def aclose(self) -> None:
        await self._searxng.aclose()

    async def health_check(self) -> HealthResult:
        return await self._searxng.health_check()


class LinkedInAdapter(SearxngDorkingAdapter):
    """LinkedIn Public & Dorking Intelligence Adapter.

    Retrieves public profiles, posts, and company updates via site-targeted SearXNG metasearch
    dorking (site:linkedin.com) and scaffolds Playwright stealth extraction.
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="linkedin",
            name="LinkedIn Public & Dorking Intelligence",
            slug="linkedin",
            category="social",
            supported_query_types=("keyword", "profile", "company"),
            supported_filters=("language", "time_range"),
            available_fields=("title", "url", "snippet", "publishedDate"),
            geographic_coverage="Global public index",
            access_requirements=("Reachable SearXNG instance",),
            rate_limit_notes="Governed by metasearch upstream engine limits",
            terms_notes="Publicly indexed search intelligence.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(config.get("q", "") or config.get("primary", "")).strip()
        if not q:
            raise UnsupportedQueryError(
                "LinkedIn query requires search keywords or a profile target"
            )
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(config.get("q", "") or config.get("primary", "")).strip()

        if "site:linkedin.com" in raw_q:
            dorked_query = raw_q
        elif config.get("kind") == "profile" or "profile" in raw_q.lower():
            dorked_query = f"site:linkedin.com/in/ {raw_q}"
        elif config.get("kind") == "company" or "company" in raw_q.lower():
            dorked_query = f"site:linkedin.com/company/ {raw_q}"
        else:
            dorked_query = f"site:linkedin.com {raw_q}"

        modified_config = {**config, "q": dorked_query}
        results = await self._searxng.search(modified_config)
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            url = r.content_url or ""
            c_type = "profile" if "/in/" in url else "company" if "/company/" in url else "post"
            author = None
            if "/in/" in url:
                parsed_path = str(urlsplit(url).path)
                author = parsed_path.strip("/").split("/")[-1]
            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=url,
                    content_type=c_type,
                    content_text=r.content_text,
                    published_at=r.published_at,
                    engagement=r.engagement,
                    author_username=author,
                    raw_data={**r.raw_data, "platform": "linkedin"},
                )
            )
        return refined


class InstagramAdapter(SearxngDorkingAdapter):
    """Instagram Public & Dorking Intelligence Adapter.

    Extracts public posts and creator accounts via SearXNG metasearch dorking (site:instagram.com).
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="instagram",
            name="Instagram Public & Dorking Intelligence",
            slug="instagram",
            category="social",
            supported_query_types=("keyword", "handle", "hashtag"),
            supported_filters=("language", "time_range"),
            available_fields=("title", "url", "snippet", "publishedDate"),
            geographic_coverage="Global public index",
            access_requirements=("Reachable SearXNG instance",),
            rate_limit_notes="Governed by metasearch upstream engine limits",
            terms_notes="Publicly indexed search intelligence.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(config.get("q", "") or config.get("primary", "")).strip()
        if not q:
            raise UnsupportedQueryError("Instagram query requires search keywords or a handle")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(config.get("q", "") or config.get("primary", "")).strip()
        dorked_query = raw_q if "site:instagram.com" in raw_q else f"site:instagram.com {raw_q}"
        results = await self._searxng.search({**config, "q": dorked_query})
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            url = r.content_url
            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=url,
                    content_type="post",
                    content_text=r.content_text,
                    published_at=r.published_at,
                    engagement=r.engagement,
                    raw_data={**r.raw_data, "platform": "instagram"},
                )
            )
        return refined


class FacebookAdapter(SearxngDorkingAdapter):
    """Facebook Public & Dorking Intelligence Adapter.

    Extracts public posts, pages, and groups via SearXNG metasearch dorking (site:facebook.com).
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="facebook",
            name="Facebook Public & Dorking Intelligence",
            slug="facebook",
            category="social",
            supported_query_types=("keyword", "page", "group"),
            supported_filters=("language", "time_range"),
            available_fields=("title", "url", "snippet", "publishedDate"),
            geographic_coverage="Global public index",
            access_requirements=("Reachable SearXNG instance",),
            rate_limit_notes="Governed by metasearch upstream engine limits",
            terms_notes="Publicly indexed search intelligence.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(config.get("q", "") or config.get("primary", "")).strip()
        if not q:
            raise UnsupportedQueryError("Facebook query requires search keywords or a page name")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(config.get("q", "") or config.get("primary", "")).strip()
        dorked_query = raw_q if "site:facebook.com" in raw_q else f"site:facebook.com {raw_q}"
        results = await self._searxng.search({**config, "q": dorked_query})
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=r.content_url,
                    content_type="post",
                    content_text=r.content_text,
                    published_at=r.published_at,
                    engagement=r.engagement,
                    raw_data={**r.raw_data, "platform": "facebook"},
                )
            )
        return refined


class XSocialAdapter(SearxngDorkingAdapter):
    """X (Twitter) Public Syndication & Dorking Adapter.

    Uses public syndication endpoints for user timelines, oEmbed for individual tweets,
    and site dorking (site:x.com OR site:twitter.com) for discovery without paid API tiers.
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="x",
            name="X (Twitter) Syndication & Dorking Intelligence",
            slug="x",
            category="social",
            supported_query_types=("keyword", "username", "url"),
            supported_filters=("language", "time_range"),
            available_fields=("text", "url", "author", "publishedDate"),
            geographic_coverage="Global public index",
            access_requirements=("Public syndication / SearXNG instance",),
            rate_limit_notes="Subject to public syndication rate limits and SearXNG engine limits",
            terms_notes="Public syndication and indexed content.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(
            config.get("q", "") or config.get("username", "") or config.get("primary", "")
        ).strip()
        if not q:
            raise UnsupportedQueryError("X query requires search keywords or a @handle")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(
            config.get("q", "") or config.get("username", "") or config.get("primary", "")
        ).strip()

        # Check if oEmbed single post is targeted
        if ("twitter.com" in raw_q or "x.com" in raw_q) and "/status/" in raw_q:
            oembed_result = await self._fetch_oembed(raw_q)
            if oembed_result is not None:
                return [oembed_result]

        # Check if syndication user timeline is requested
        username = config.get("username")
        if not username and raw_q.startswith("@") and " " not in raw_q:
            username = raw_q.lstrip("@")

        if username:
            timeline_results = await self._fetch_syndication_timeline(str(username))
            if timeline_results:
                return timeline_results

        # Fallback to SearXNG site dorking
        if "site:x.com" in raw_q or "site:twitter.com" in raw_q:
            dorked_query = raw_q
        else:
            dorked_query = f"(site:x.com OR site:twitter.com) {raw_q}"

        results = await self._searxng.search({**config, "q": dorked_query})
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            url = r.content_url or ""
            author = None
            if "status/" in url:
                parsed_path = str(urlsplit(url).path)
                parts = parsed_path.strip("/").split("/")
                if len(parts) >= 2:
                    author = parts[0]
            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=url,
                    content_type="post",
                    content_text=r.content_text,
                    published_at=r.published_at,
                    author_username=author,
                    engagement=r.engagement,
                    raw_data={**r.raw_data, "platform": "x"},
                )
            )
        return refined

    async def _fetch_oembed(self, tweet_url: str) -> SocialResult | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://publish.twitter.com/oembed",
                    params={"url": tweet_url, "omit_script": "true"},
                    headers={"User-Agent": self._user_agent},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    author_name = data.get("author_name")
                    html = data.get("html", "")
                    snippet_part = (
                        html.split("<p lang=")[-1].split("</p>")[0] if "<p" in html else html
                    )
                    clean_text = sanitize_text(snippet_part)
                    return SocialResult(
                        external_id=canonical_hash(tweet_url),
                        content_url=tweet_url,
                        content_type="post",
                        content_text=clean_text or data.get("title"),
                        published_at=None,
                        author_display_name=author_name,
                        author_profile_url=data.get("author_url"),
                        engagement={},
                        raw_data=data,
                    )
        except Exception:  # noqa: BLE001 - fallback
            return None
        return None

    async def _fetch_syndication_timeline(self, username: str) -> list[SocialResult] | None:
        try:
            url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"User-Agent": self._user_agent})
                if resp.status_code == 200 and "__NEXT_DATA__" in resp.text:
                    import json
                    text_html = resp.text
                    parts = text_html.split('<script id="__NEXT_DATA__" type="application/json">')
                    json_str = parts[1].split("</script>")[0]
                    data = json.loads(json_str)
                    timeline = data.get("props", {}).get("pageProps", {}).get("timeline", {})
                    entries = timeline.get("entries", [])
                    results: list[SocialResult] = []
                    for entry in entries:
                        tweet = entry.get("content", {}).get("tweet", {})
                        if not tweet:
                            continue
                        tid = str(tweet.get("id_str") or tweet.get("id"))
                        t_text = tweet.get("text", "")
                        t_user = tweet.get("user", {})
                        t_url = f"https://x.com/{t_user.get('screen_name', username)}/status/{tid}"
                        results.append(
                            SocialResult(
                                external_id=canonical_hash(t_url),
                                content_url=t_url,
                                content_type="post",
                                content_text=sanitize_text(t_text),
                                published_at=_parse_iso_str(tweet.get("created_at")),
                                author_username=t_user.get("screen_name"),
                                author_display_name=t_user.get("name"),
                                engagement={"favorite_count": tweet.get("favorite_count", 0)},
                                raw_data=tweet,
                            )
                        )
                    if results:
                        return results
        except Exception:  # noqa: BLE001 - fallback
            return None
        return None


class YouTubeAdapter(SearxngDorkingAdapter):
    """YouTube Public RSS, oEmbed & Dorking Adapter.

    Extracts videos and channel metadata using YouTube public RSS feeds,
    oEmbed endpoints, and SearXNG metasearch dorking (site:youtube.com).
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="youtube",
            name="YouTube Video & Channel Intelligence",
            slug="youtube",
            category="social",
            supported_query_types=("keyword", "channel_id", "url"),
            supported_filters=("language", "time_range"),
            available_fields=("title", "url", "snippet", "publishedDate", "author"),
            geographic_coverage="Global video index",
            access_requirements=("Public RSS / SearXNG metasearch",),
            rate_limit_notes="Subject to public RSS rate limits and metasearch limits",
            terms_notes="Publicly accessible video metadata and channel feeds.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(
            config.get("q", "") or config.get("channel_id", "") or config.get("primary", "")
        ).strip()
        if not q:
            raise UnsupportedQueryError("YouTube query requires search keywords or a channel ID")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(
            config.get("q", "") or config.get("channel_id", "") or config.get("primary", "")
        ).strip()

        # Check if single video URL
        if "youtube.com/watch" in raw_q or "youtu.be/" in raw_q:
            oembed = await self._fetch_oembed(raw_q)
            if oembed is not None:
                return [oembed]

        # Check if channel ID RSS feed
        channel_id = config.get("channel_id")
        if not channel_id and "UC" in raw_q and len(raw_q) == 24:
            channel_id = raw_q

        if channel_id:
            rss_results = await self._fetch_channel_rss(str(channel_id))
            if rss_results:
                return rss_results

        # Fallback to SearXNG site dorking
        dorked_query = raw_q if "site:youtube.com" in raw_q else f"site:youtube.com {raw_q}"
        results = await self._searxng.search({**config, "q": dorked_query})
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=r.content_url,
                    content_type="video",
                    content_text=r.content_text,
                    published_at=r.published_at,
                    engagement=r.engagement,
                    raw_data={**r.raw_data, "platform": "youtube"},
                )
            )
        return refined

    async def _fetch_oembed(self, video_url: str) -> SocialResult | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://www.youtube.com/oembed",
                    params={"url": video_url, "format": "json"},
                    headers={"User-Agent": self._user_agent},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return SocialResult(
                        external_id=canonical_hash(video_url),
                        content_url=video_url,
                        content_type="video",
                        content_text=data.get("title"),
                        published_at=None,
                        author_display_name=data.get("author_name"),
                        author_profile_url=data.get("author_url"),
                        engagement={},
                        raw_data=data,
                    )
        except Exception:  # noqa: BLE001 - fallback
            return None
        return None

    async def _fetch_channel_rss(self, channel_id: str) -> list[SocialResult] | None:
        try:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"User-Agent": self._user_agent})
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    results: list[SocialResult] = []
                    for entry in root.findall("atom:entry", ns):
                        link_el = entry.find("atom:link", ns)
                        v_url = link_el.attrib.get("href") if link_el is not None else ""
                        title_el = entry.find("atom:title", ns)
                        v_title = title_el.text if title_el is not None else ""
                        published_el = entry.find("atom:published", ns)
                        v_pub = (
                            _parse_iso_str(published_el.text)
                            if published_el is not None
                            else None
                        )
                        author_el = entry.find("atom:author/atom:name", ns)
                        v_author = author_el.text if author_el is not None else None
                        if v_url:
                            results.append(
                                SocialResult(
                                    external_id=canonical_hash(v_url),
                                    content_url=v_url,
                                    content_type="video",
                                    content_text=sanitize_text(v_title),
                                    published_at=v_pub,
                                    author_display_name=v_author,
                                    engagement={},
                                    raw_data={"channel_id": channel_id},
                                )
                            )
                    return results
        except Exception:  # noqa: BLE001 - fallback
            return None
        return None




class JustdialAdapter(SearxngDorkingAdapter):
    """Justdial and Public Local Directory Adapter.

    Discovers publicly indexed listings via site-targeted SearXNG metasearch dorking
    (site:justdial.com) and extracts business details (name, address, phone, rating, website).
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="justdial",
            name="Justdial & Public Directories",
            slug="justdial",
            category="social",
            supported_query_types=("keyword", "business"),
            supported_filters=("language", "time_range"),
            available_fields=("name", "phone", "website", "address", "rating", "review_count"),
            geographic_coverage="India & regional local business directories",
            access_requirements=("Reachable SearXNG instance",),
            rate_limit_notes="Governed by metasearch upstream engine limits",
            terms_notes="Publicly indexed search intelligence.",
            max_results_per_query=self._results_per_page,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        q = str(config.get("q", "") or config.get("primary", "")).strip()
        if not q:
            raise UnsupportedQueryError("Justdial query requires search keywords or a business target")
        if len(q) > MAX_QUERY_LENGTH:
            raise UnsupportedQueryError(f"Query is {len(q)} chars; limit is {MAX_QUERY_LENGTH}")

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        await self.validate_config(config)
        raw_q = str(config.get("q", "") or config.get("primary", "")).strip()
        if "site:justdial.com" in raw_q:
            dorked_query = raw_q
        else:
            dorked_query = f"site:justdial.com {raw_q}"

        modified_config = {**config, "q": dorked_query}
        results = await self._searxng.search(modified_config)
        self.requests_made += self._searxng.requests_made

        refined: list[SocialResult] = []
        for r in results:
            url = r.content_url or ""
            biz_details: dict[str, Any] = {}
            if url and "justdial.com" in url:
                try:
                    from app.modules.discovery.public_fetch import fetch_public_page
                    fetch_res = await fetch_public_page(url)
                    if fetch_res.status == "full_text" and fetch_res.body_text:
                        import json
                        import re
                        json_ld_matches = re.findall(r"""<script[^>]*type=['"]application/ld\+json['"][^>]*>(.*?)</script>""",
                            fetch_res.body_text,
                            re.DOTALL | re.IGNORECASE,
                        )
                        for raw_ld in json_ld_matches:
                            try:
                                ld = json.loads(raw_ld.strip())
                                if isinstance(ld, dict) and any(
                                    t in str(ld.get("@type", ""))
                                    for t in ("LocalBusiness", "Store", "Organization", "Restaurant")
                                ):
                                    biz_details["name"] = ld.get("name")
                                    biz_details["phone"] = ld.get("telephone")
                                    biz_details["website_url"] = ld.get("url")
                                    if isinstance(ld.get("aggregateRating"), dict):
                                        biz_details["rating"] = ld["aggregateRating"].get("ratingValue")
                                        biz_details["review_count"] = ld["aggregateRating"].get("reviewCount")
                                    if isinstance(ld.get("address"), dict):
                                        addr = ld["address"]
                                        biz_details["address"] = (
                                            f"{addr.get('streetAddress', '')}, {addr.get('addressLocality', '')}, {addr.get('postalCode', '')}"
                                        ).strip(" ,")
                                    break
                            except Exception:
                                pass
                except Exception:
                    pass

            refined.append(
                SocialResult(
                    external_id=r.external_id,
                    content_url=url,
                    content_type="directory_listing",
                    content_text=r.content_text,
                    published_at=r.published_at,
                    engagement=r.engagement,
                    author_display_name=biz_details.get("name") or r.author_display_name,
                    raw_data={
                        **r.raw_data,
                        "platform": "justdial",
                        "business_details": biz_details,
                    },
                )
            )
        return refined

ADAPTER_REGISTRY: dict[str, str] = {
    "reddit": "RedditAdapter",
    "hackernews": "HackerNewsAdapter",
    "rss": "RssAtomAdapter",
    "searxng": "SearxngSocialAdapter",
    "stackoverflow": "StackOverflowAdapter",
    "bluesky": "BlueskyAdapter",
    "mastodon": "MastodonAdapter",
    "linkedin": "LinkedInAdapter",
    "instagram": "InstagramAdapter",
    "facebook": "FacebookAdapter",
    "x": "XSocialAdapter",
    "youtube": "YouTubeAdapter",
    "justdial": "JustdialAdapter",
}
