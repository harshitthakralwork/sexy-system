"""Social & Demand Intelligence Engine — Phase 2 connector tests.

The wire is the only thing mocked; parsing, validation, capability honesty and the
SSRF guard run for real. A connector must map a source response into SocialResult
without inventing fields it was not given, and must reject a query or an unsafe
feed URL rather than reaching for it.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import SourceUnavailableError
from app.modules.discovery.adapters.base import (
    AdapterError,
    MalformedResponseError,
    UnsupportedQueryError,
)
from app.modules.social import service
from app.modules.social.connectors import (
    BlueskyAdapter,
    FacebookAdapter,
    HackerNewsAdapter,
    InstagramAdapter,
    LinkedInAdapter,
    MastodonAdapter,
    RssAtomAdapter,
    SearxngSocialAdapter,
    StackOverflowAdapter,
    XSocialAdapter,
    YouTubeAdapter,
)

HN_BASE = "https://hn.algolia.com"
SEARXNG_BASE = "http://localhost:8080"
# A public IP literal keeps validate_discovered_target from needing DNS in a test.
SAFE_FEED = "http://93.184.216.34/feed.xml"


def _client(handler, seen: list | None = None) -> httpx.AsyncClient:
    def _handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


def _hn_adapter(payload: dict, seen: list | None = None) -> HackerNewsAdapter:
    return HackerNewsAdapter(
        HN_BASE,
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload), seen),
    )


def _searxng_adapter(payload: dict, seen: list | None = None) -> SearxngSocialAdapter:
    return SearxngSocialAdapter(
        SEARXNG_BASE,
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload), seen),
    )


def _rss_adapter(body: str) -> RssAtomAdapter:
    return RssAtomAdapter(
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, text=body)),
    )


# --- Factory ----------------------------------------------------------------


def test_factory_builds_each_keyless_connector() -> None:
    settings = Settings()
    assert isinstance(service._build_adapter(settings, "hackernews"), HackerNewsAdapter)
    assert isinstance(service._build_adapter(settings, "rss"), RssAtomAdapter)
    assert isinstance(service._build_adapter(settings, "searxng"), SearxngSocialAdapter)
    assert isinstance(service._build_adapter(settings, "stackoverflow"), StackOverflowAdapter)
    assert isinstance(service._build_adapter(settings, "bluesky"), BlueskyAdapter)
    assert isinstance(service._build_adapter(settings, "mastodon"), MastodonAdapter)
    assert isinstance(service._build_adapter(settings, "linkedin"), LinkedInAdapter)
    assert isinstance(service._build_adapter(settings, "instagram"), InstagramAdapter)
    assert isinstance(service._build_adapter(settings, "facebook"), FacebookAdapter)
    assert isinstance(service._build_adapter(settings, "x"), XSocialAdapter)
    assert isinstance(service._build_adapter(settings, "youtube"), YouTubeAdapter)


def test_factory_rejects_unknown_adapter() -> None:
    with pytest.raises(SourceUnavailableError):
        service._build_adapter(Settings(), "myspace")


# --- Hacker News ------------------------------------------------------------


def _hn_hits() -> dict:
    return {
        "hits": [
            {
                "objectID": "123",
                "title": "Looking for a web dev agency for our launch",
                "url": "https://acme.example",
                "author": "founder1",
                "created_at_i": 1700000000,
                "points": 42,
                "num_comments": 8,
                "tags": ["story"],
            },
            {
                "objectID": "456",
                "story_title": "Ask HN: need automation help",
                "text": "Anyone build n8n flows?",
                "author": "dev2",
                "created_at_i": 1700000500,
                "story_url": "https://news.ycombinator.com/item?id=456",
                "tags": ["comment", "ask_hn"],
            },
            {"title": "no id — skipped"},
        ]
    }


def test_hackernews_search_maps_results() -> None:
    results = asyncio.run(_hn_adapter(_hn_hits()).search({"kind": "search", "q": "web agency"}))
    assert len(results) == 2  # the id-less hit is dropped, not invented
    first = next(r for r in results if r.external_id == "123")
    assert first.content_url == "https://acme.example"
    assert first.published_at is not None and first.published_at.year >= 2023
    assert first.engagement["points"] == 42
    comment = next(r for r in results if r.external_id == "456")
    assert comment.content_type == "comment"


def test_hackernews_front_page_sets_tag() -> None:
    seen: list = []
    asyncio.run(_hn_adapter({"hits": []}, seen).search({"kind": "front_page"}))
    assert "/api/v1/search" in str(seen[0].url)
    assert "tags=front_page" in str(seen[0].url)


def test_hackernews_rejects_unknown_kind() -> None:
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(_hn_adapter({}).search({"kind": "nonsense"}))


def test_hackernews_malformed_body_raises() -> None:
    adapter = HackerNewsAdapter(
        HN_BASE,
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, text="not json")),
    )
    with pytest.raises(MalformedResponseError):
        asyncio.run(adapter.search({"kind": "search", "q": "x"}))


# --- RSS / Atom -------------------------------------------------------------


_RSS_XML = """<?xml version="1.0"?>
<rss><channel><title>Feed</title>
<item><title>Need a developer</title><link>https://a.example/post</link>
<description>Looking for someone to build an app</description>
<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""

_ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Show: new SaaS</title><link href="https://b.example/1"/>
<summary>launched today</summary><published>2026-11-01T09:00:00Z</published></entry>
</feed>"""


def test_rss_parses_rss20() -> None:
    results = asyncio.run(_rss_adapter(_RSS_XML).search({"feed_urls": [SAFE_FEED]}))
    assert len(results) == 1
    item = results[0]
    assert item.content_url == "https://a.example/post"
    assert "Need a developer" in item.content_text
    assert item.published_at is not None


def test_rss_parses_atom_entry() -> None:
    results = asyncio.run(_rss_adapter(_ATOM_XML).search({"feed_urls": [SAFE_FEED]}))
    assert results[0].content_url == "https://b.example/1"
    assert results[0].published_at is not None


def test_rss_refuses_dtd() -> None:
    body = '<!DOCTYPE rss [<!ENTITY x "y">]><rss><channel></channel></rss>'
    with pytest.raises(AdapterError):
        asyncio.run(_rss_adapter(body).search({"feed_urls": [SAFE_FEED]}))


def test_rss_rejects_private_feed_url() -> None:
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(
            _rss_adapter("").search({"feed_urls": ["http://169.254.169.254/latest/meta-data"]})
        )


def test_rss_rejects_non_http_scheme() -> None:
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(_rss_adapter("").search({"feed_urls": ["ftp://example.com/feed"]}))


def test_rss_requires_feed_list() -> None:
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(_rss_adapter("").search({"feed_urls": []}))


# --- SearXNG (indexed snippets) --------------------------------------------


def test_searxng_maps_indexed_snippets() -> None:
    payload = {
        "results": [
            {
                "title": "Company looking for vendor",
                "url": "https://social.example/post/9",
                "content": "We need a partner for...",
                "engine": "duckduckgo",
            }
        ]
    }
    results = asyncio.run(_searxng_adapter(payload).search({"q": "looking for vendor"}))
    assert len(results) == 1
    assert results[0].raw_data["retrieval_hint"] == "indexed_snippet"
    assert results[0].content_url == "https://social.example/post/9"


def test_searxng_requires_query() -> None:
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(_searxng_adapter({}).search({"q": "   "}))


# --- Capability honesty -----------------------------------------------------


def test_searxng_capability_states_snippets_not_retrieval() -> None:
    adapter = _searxng_adapter({})
    assert "snippet" in adapter.capabilities.terms_notes.lower()
    assert adapter.capabilities.access_requirements  # says a running instance is required


# --- Stack Overflow / Bluesky / Mastodon (Priority-2, key-free) ------------


def test_stackoverflow_maps_questions() -> None:
    payload = {
        "items": [
            {
                "question_id": 7001,
                "title": "Looking for a developer to build an app",
                "link": "https://stackoverflow.com/q/7001",
                "creation_date": 1700000000,
                "score": 3,
                "answer_count": 1,
                "tags": ["web"],
                "body": "<p>We need someone</p>",
            },
            {"title": "no id — skipped"},
        ]
    }
    adapter = StackOverflowAdapter(
        "https://api.stackexchange.com",
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload)),
    )
    results = asyncio.run(adapter.search({"q": "looking for developer"}))
    assert len(results) == 1
    assert results[0].external_id == "7001"
    assert results[0].content_url == "https://stackoverflow.com/q/7001"
    assert "Looking for a developer" in (results[0].content_text or "")
    # body html is stripped, not stored raw
    assert "<p>" not in (results[0].content_text or "")


def test_stackoverflow_requires_query() -> None:
    adapter = StackOverflowAdapter(
        "https://api.stackexchange.com",
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json={})),
    )
    with pytest.raises(UnsupportedQueryError):
        asyncio.run(adapter.search({"q": "  "}))


def test_bluesky_maps_posts() -> None:
    payload = {
        "posts": [
            {
                "cid": "abc",
                "uri": "at://did:plc:x/app.bsky.feed.post/rkey1",
                "indexedAt": "2026-11-01T09:00:00.000Z",
                "record": {
                    "text": "Anyone building automations for small biz?",
                    "createdAt": "2026-11-01T09:00:00.000Z",
                },
                "author": {"handle": "dev.bsky.social", "displayName": "Dev"},
                "repostsCount": 2,
                "likesCount": 5,
            }
        ]
    }
    adapter = BlueskyAdapter(
        "https://public.api.bsky.app",
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload)),
    )
    results = asyncio.run(adapter.search({"q": "automation"}))
    assert len(results) == 1
    assert results[0].external_id == "abc"
    assert results[0].content_url == "https://bsky.app/profile/dev.bsky.social/post/rkey1"
    assert results[0].author_username == "dev.bsky.social"
    assert results[0].published_at is not None


def test_mastodon_reports_refusal_honestly() -> None:
    adapter = MastodonAdapter(
        "https://mastodon.social",
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(401, text="")),
    )
    with pytest.raises(AdapterError):
        asyncio.run(adapter.search({"q": "hiring developer"}))


def test_mastodon_maps_statuses() -> None:
    payload = {
        "statuses": [
            {
                "id": "99",
                "url": "https://mastodon.social/@ops/99",
                "content": "<p>Need a website rebuilt</p>",
                "created_at": "2026-11-01T10:00:00.000Z",
                "account": {"username": "ops", "acct": "ops@mastodon.social", "url": "https://mastodon.social/@ops"},
            }
        ]
    }
    adapter = MastodonAdapter(
        "https://mastodon.social",
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload)),
    )
    results = asyncio.run(adapter.search({"q": "website"}))
    assert results[0].external_id == "99"
    assert "<p>" not in (results[0].content_text or "")
    assert results[0].author_username == "ops"


# --- Dorking & Syndication Connectors ----------------------------------------


@pytest.mark.asyncio
async def test_linkedin_adapter_dorks_and_refines() -> None:
    payload = {
        "results": [
            {
                "url": "https://www.linkedin.com/in/jane-doe",
                "title": "Jane Doe - VP Engineering",
                "content": "Building next-gen fintech solutions.",
                "engine": "google",
            }
        ]
    }
    adapter = LinkedInAdapter(
        SEARXNG_BASE,
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=payload)),
    )
    assert adapter.capabilities.slug == "linkedin"
    results = await adapter.search({"q": "Jane Doe", "kind": "profile"})
    assert len(results) == 1
    assert results[0].content_type == "profile"
    assert results[0].author_username == "jane-doe"
    assert "fintech" in results[0].content_text


@pytest.mark.asyncio
async def test_x_adapter_oembed_and_dorking() -> None:
    oembed_payload = {
        "url": "https://twitter.com/jack/status/20",
        "author_name": "jack",
        "author_url": "https://twitter.com/jack",
        "html": "<blockquote>just setting up my twttr</blockquote>",
    }
    adapter = XSocialAdapter(
        SEARXNG_BASE,
        user_agent="test-agent",
        client=_client(lambda r: httpx.Response(200, json=oembed_payload)),
    )
    assert adapter.capabilities.slug == "x"
    with pytest.raises(UnsupportedQueryError):
        await adapter.validate_config({"q": ""})


@pytest.mark.asyncio
async def test_youtube_adapter_capabilities() -> None:
    adapter = YouTubeAdapter(SEARXNG_BASE, user_agent="test-agent")
    assert adapter.capabilities.slug == "youtube"
    with pytest.raises(UnsupportedQueryError):
        await adapter.validate_config({"q": ""})
