from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.modules.discovery.adapters.base import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_WORKING,
    AccessDeniedError,
    AdapterCapabilities,
    AdapterError,
    HealthResult,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.shared.url_safety import validate_service_base_url

# Hard ceilings, independent of configuration. A single unauthenticated request
# against Reddit's public JSON is already rate-limited by IP; pagination would
# multiply that against shared infrastructure for no honest gain.
MAX_RESULTS_LIMIT = 100
MAX_QUERY_LENGTH = 300
VALID_SORTS = ("relevance", "hot", "new", "top", "comments")


@dataclass(frozen=True)
class SocialResult:
    """One item exactly as the platform returned it — nothing normalised, nothing judged."""

    external_id: str
    content_url: str | None
    content_type: str
    content_text: str | None
    published_at: datetime | None
    engagement: dict[str, Any] = field(default_factory=dict)
    author_external_id: str | None = None
    author_username: str | None = None
    author_profile_url: str | None = None
    author_display_name: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class SocialAdapter(Protocol):
    """Contract a social platform adapter implements (architecture.md section 15).

    An adapter must not raise for "no results" — an empty list is an honest
    outcome. A failure (blocked, rate-limited, malformed) must raise AdapterError.
    """

    @property
    def capabilities(self) -> AdapterCapabilities: ...

    async def search(self, config: dict[str, Any]) -> list[SocialResult]: ...

    async def health_check(self) -> HealthResult: ...


def _raise_for_source_response(response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    if response.status_code == 429:
        raise RateLimitedError("Reddit rate-limited this client (HTTP 429)")
    if response.status_code in (401, 403):
        raise AccessDeniedError(
            f"Reddit refused the request ({response.status_code}). "
            "Unauthenticated JSON access may be blocked for this client."
        )
    if response.status_code == 400:
        raise UnsupportedQueryError("Reddit rejected the query parameters")
    raise AdapterError(f"Reddit returned HTTP {response.status_code}", classification="http_error")


def _require_agent(adapter: RedditAdapter) -> None:
    if not adapter._user_agent.strip():
        raise AdapterError(
            "A descriptive User-Agent is required for Reddit's public API",
            classification="misconfigured",
        )


class RedditAdapter:
    """Reddit discovery through its unauthenticated public JSON endpoints.

    This is the one initial platform with a permitted, key-free access method.
    It collects public posts and comments only, with a descriptive User-Agent,
    one request per run — no authentication, no workaround, no scraping of pages.
    """

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        origin = validate_service_base_url(base_url, field="Reddit base_url")
        self._base_url = origin
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="reddit",
            name="Reddit (public JSON)",
            slug="reddit",
            category="social",
            supported_query_types=("keyword", "subreddit", "username"),
            supported_filters=("sort",),
            available_fields=("title", "selftext", "author", "score", "created_utc", "permalink"),
            geographic_coverage="Global; no geographic filter is available on the public API.",
            access_requirements=("A descriptive User-Agent",),
            rate_limit_notes=(
                "Unauthenticated JSON is throttled per IP (~10 requests/minute). "
                "One request per run on purpose."
            ),
            terms_notes="Reddit's API terms apply; public content only.",
            max_results_per_query=MAX_RESULTS_LIMIT,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        self._validate_query_config(config)

    def _validate_query_config(self, config: dict[str, Any]) -> None:
        kind = str(config.get("kind", "search"))
        if kind not in ("search", "subreddit", "user"):
            raise UnsupportedQueryError(f"Unsupported query kind: {kind}")
        if kind == "search":
            q = str(config.get("q", "")).strip()
            if not q:
                raise UnsupportedQueryError("A keyword search needs a non-empty 'q'")
            if len(q) > MAX_QUERY_LENGTH:
                raise UnsupportedQueryError(
                    f"Search term is {len(q)} characters; the limit is {MAX_QUERY_LENGTH}"
                )
        elif kind == "subreddit":
            sub = str(config.get("subreddit", "")).strip()
            if not sub:
                raise UnsupportedQueryError("A subreddit query needs a 'subreddit'")
            q = str(config.get("q", "")).strip()
            if q and len(q) > MAX_QUERY_LENGTH:
                raise UnsupportedQueryError(f"Search term is too long (limit {MAX_QUERY_LENGTH})")
        elif kind == "user":
            username = str(config.get("username", "")).strip()
            if not username:
                raise UnsupportedQueryError("A user query needs a 'username'")
        sort = str(config.get("sort", "relevance"))
        if sort not in VALID_SORTS:
            raise UnsupportedQueryError(f"Unsupported sort: {sort}")
        limit = int(config.get("limit", 25))
        if not 1 <= limit <= MAX_RESULTS_LIMIT:
            raise UnsupportedQueryError(f"limit must be between 1 and {MAX_RESULTS_LIMIT}")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        headers = {"User-Agent": self._user_agent}
        self._client = httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=False, headers=headers
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _url_and_params(self, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        kind = config.get("kind", "search")
        sort = str(config.get("sort", "relevance"))
        limit = int(config.get("limit", 25))
        params: dict[str, Any] = {"limit": limit, "sort": sort}
        if kind == "search":
            return "/search.json", {**params, "q": str(config["q"]).strip()}
        if kind == "subreddit":
            sub = str(config["subreddit"]).strip()
            q = str(config.get("q", "")).strip()
            if q:
                return f"/r/{sub}/search.json", {
                    **params,
                    "q": q,
                    "restrict_sr": "1",
                }
            return f"/r/{sub}/{sort}.json", params
        # kind == "user"
        username = str(config["username"]).strip()
        return f"/user/{username}/submitted.json", params

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        self._validate_query_config(config)
        _require_agent(self)
        client = await self._get_client()
        path, params = self._url_and_params(config)
        response = await client.get(f"{self._base_url}{path}", params=params)
        self.requests_made += 1
        _raise_for_source_response(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError(
                "Reddit replied with a non-JSON body; the public endpoint may be unavailable."
            ) from exc
        return self._to_results(payload)

    def _to_results(self, payload: Any) -> list[SocialResult]:
        if not isinstance(payload, dict) or payload.get("kind") != "Listing":
            raise MalformedResponseError("Reddit response was not a Listing")
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("children"), list):
            raise MalformedResponseError("Reddit Listing had no children array")
        results: list[SocialResult] = []
        for child in data["children"]:
            if not isinstance(child, dict):
                continue
            post = child.get("data")
            if not isinstance(post, dict):
                continue
            post_id = post.get("id")
            if not post_id:
                continue
            permalink = post.get("permalink")
            content_url = (
                f"{self._base_url}{permalink}" if isinstance(permalink, str) else None
            )
            created = post.get("created_utc")
            published_at = None
            if isinstance(created, (int, float)):
                published_at = datetime.fromtimestamp(created, tz=UTC)
            title = str(post.get("title") or "").strip()
            selftext = str(post.get("selftext") or "").strip()
            text = "\n\n".join(part for part in (title, selftext) if part) or None
            author = post.get("author")
            author_name = (
                author
                if isinstance(author, str) and author not in ("[deleted]", "[removed]")
                else None
            )
            results.append(
                SocialResult(
                    external_id=str(post_id),
                    content_url=content_url,
                    content_type="post",
                    content_text=text,
                    published_at=published_at,
                    engagement={
                        "score": post.get("score"),
                        "num_comments": post.get("num_comments"),
                        "upvote_ratio": post.get("upvote_ratio"),
                        "subreddit": post.get("subreddit"),
                    },
                    author_external_id=author_name,
                    author_username=author_name,
                    author_profile_url=(
                        f"{self._base_url}/user/{author_name}" if author_name else None
                    ),
                    author_display_name=author_name,
                    raw_data=post,
                )
            )
        return results

    async def health_check(self) -> HealthResult:
        started = time.perf_counter()
        _require_agent(self)
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self._base_url}/r/announcements.json", params={"limit": "1"}
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            _raise_for_source_response(response)
            try:
                payload = response.json()
            except ValueError:
                return HealthResult(
                    status=HEALTH_DEGRADED,
                    detail="Responding, but not returning JSON",
                    response_time_ms=elapsed,
                )
            if not isinstance(payload, dict) or payload.get("kind") != "Listing":
                return HealthResult(
                    status=HEALTH_DEGRADED,
                    detail="Responding, but not returning a Listing",
                    response_time_ms=elapsed,
                )
            return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except httpx.HTTPError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - a health probe reports, never raises
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
