"""Phase 4: social intelligence — platform catalogue, research queries, content.

Every test drives the HTTP API against real persistence. The Reddit network call
is replaced with an ``httpx.MockTransport`` so the real adapter validation and
response parsing still run; only the wire is stubbed. Ownership is the core
invariant: another user's queries and content must be invisible.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.social import service
from app.modules.social.adapters import RedditAdapter
from tests.conftest import Session


def _post(
    post_id: str,
    *,
    title: str = "A post",
    author: str = "alice",
    subreddit: str = "test",
    **extra,
) -> dict:
    return {
        "id": post_id,
        "permalink": f"/r/{subreddit}/comments/{post_id}/slug/",
        "title": title,
        "selftext": "body text",
        "author": author,
        "score": 42,
        "num_comments": 3,
        "upvote_ratio": 0.95,
        "subreddit": subreddit,
        "created_utc": 1700000000,
        **extra,
    }


def _install_reddit_transport(
    monkeypatch: pytest.MonkeyPatch,
    *,
    posts: list[dict] | None = None,
    status: int = 200,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, request=request)
        payload = {
            "kind": "Listing",
            "data": {"children": [{"data": p} for p in (posts or [])]},
        }
        return httpx.Response(200, json=payload, request=request)

    def build(settings, adapter_key):
        assert adapter_key == "reddit"
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False
        )
        adapter = RedditAdapter(
            settings.reddit_base_url,
            user_agent=settings.reddit_user_agent,
            timeout_seconds=settings.reddit_timeout_seconds,
            client=client,
        )
        # aclose() must close the injected client so tests never leak it.
        adapter._owns_client = True
        return adapter

    monkeypatch.setattr(service, "_build_adapter", build)


def _create_query(
    account: Session, *, platform_slug: str = "reddit", **config
) -> dict:
    query_config = {"kind": "search", "q": "fintech india", "sort": "new", **config}
    response = account.api.post(
        "/api/v1/social/research-queries",
        json={"platform_slug": platform_slug, "query_config": query_config},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _insert_business(owner_id: str, *, name: str = "Spark Cafe") -> str:
    async def run() -> str:
        async with session_scope() as db:
            business = Business(
                owner_user_id=uuid.UUID(owner_id),
                name=name,
                normalized_name=name.lower(),
                first_discovered_at=datetime.now(UTC),
            )
            db.add(business)
            await db.flush()
            return str(business.id)

    return asyncio.run(run())


def test_platform_catalogue_seeds_honestly(session_account: Session) -> None:
    listed = session_account.api.get("/api/v1/social/platforms")
    assert listed.status_code == 200
    body = listed.json()
    # All 12 platforms are now enabled via public endpoints, dorking adapters, and syndication.
    assert len(body) == 12
    by_slug = {row["slug"]: row for row in body}
    for slug in (
        "reddit", "hackernews", "rss", "searxng", "stackoverflow", "bluesky", "mastodon",
        "linkedin", "instagram", "facebook", "x", "youtube"
    ):
        assert by_slug[slug]["is_enabled"] is True, slug
        assert by_slug[slug]["adapter_key"] == slug, slug
        assert by_slug[slug]["limitations"], slug


def test_disabled_platform_rejected(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch)
    from app.modules.social import service
    orig_get = service._get_platform_by_slug

    async def mock_get(session, slug):
        plat = await orig_get(session, slug)
        if plat and slug == "reddit":
            plat.is_enabled = False
        return plat

    monkeypatch.setattr(service, "_get_platform_by_slug", mock_get)
    response = session_account.api.post(
        "/api/v1/social/research-queries",
        json={"platform_slug": "reddit", "query_config": {"kind": "search", "q": "x"}},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 409, response.text


def test_invalid_query_config_rejected(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch)
    response = session_account.api.post(
        "/api/v1/social/research-queries",
        json={"platform_slug": "reddit", "query_config": {"kind": "search", "q": ""}},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_create_list_and_delete_query(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch)
    created = _create_query(session_account)
    assert created["platform_slug"] == "reddit"
    assert created["query_config"]["q"] == "fintech india"
    assert created["last_run_status"] is None

    listed = session_account.api.get("/api/v1/social/research-queries")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    deleted = session_account.api.delete(
        f"/api/v1/social/research-queries/{created['id']}",
        headers=session_account.csrf_headers(),
    )
    assert deleted.status_code == 200
    assert session_account.api.get("/api/v1/social/research-queries").json()["total"] == 0


def test_run_stores_content_and_dedups(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(
        monkeypatch,
        posts=[_post("abc123", title="First"), _post("def456", title="Second", author="bob")],
    )
    query = _create_query(session_account)

    first = session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )
    assert first.status_code == 200, first.text
    run = first.json()
    assert run["status"] == "completed"
    assert run["collected"] == 2
    assert run["stored_new"] == 2
    assert run["duplicates"] == 0

    content = session_account.api.get("/api/v1/social/content")
    assert content.status_code == 200
    body = content.json()
    assert body["total"] == 2
    authors = {item["author_username"] for item in body["items"]}
    assert authors == {"alice", "bob"}
    assert all(item["platform_slug"] == "reddit" for item in body["items"])

    second = session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )
    assert second.json()["stored_new"] == 0
    assert second.json()["duplicates"] == 2
    assert session_account.api.get("/api/v1/social/content").json()["total"] == 2


def test_run_failure_marks_status(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch, status=429)
    query = _create_query(session_account)

    run = session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "failed"

    listed = session_account.api.get("/api/v1/social/research-queries").json()
    assert listed["items"][0]["last_run_status"] == "failed"


def test_cross_owner_isolation(
    session_account: Session,
    make_account: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_reddit_transport(monkeypatch, posts=[_post("iso1")])
    owner = session_account
    other = make_account()

    query = _create_query(owner)
    owner.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=owner.csrf_headers(),
    )

    assert owner.api.get("/api/v1/social/content").json()["total"] == 1
    assert other.api.get("/api/v1/social/content").json()["total"] == 0
    assert other.api.get("/api/v1/social/research-queries").json()["total"] == 0


def test_content_filter_by_type(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch, posts=[_post("filter1")])
    query = _create_query(session_account)
    session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )

    posts = session_account.api.get(
        "/api/v1/social/content", params={"content_type": "post"}
    ).json()
    assert posts["total"] == 1
    none = session_account.api.get(
        "/api/v1/social/content", params={"content_type": "comment"}
    ).json()
    assert none["total"] == 0


def test_link_content_to_business(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch, posts=[_post("linkme", author="sparkx")])
    query = _create_query(session_account)
    session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )
    content_id = session_account.api.get("/api/v1/social/content").json()["items"][0]["id"]

    business_id = _insert_business(session_account.user_id)
    linked = session_account.api.post(
        f"/api/v1/social/content/{content_id}/link",
        json={"business_id": business_id},
        headers=session_account.csrf_headers(),
    )
    assert linked.status_code == 200, linked.text
    body = linked.json()
    assert body["platform"] == "reddit"
    assert body["profile_url"].startswith("https://www.reddit.com/")


def test_export_content_is_csv(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_reddit_transport(monkeypatch, posts=[_post("csv1")])
    query = _create_query(session_account)
    session_account.api.post(
        f"/api/v1/social/research-queries/{query['id']}/run",
        headers=session_account.csrf_headers(),
    )
    exported = session_account.api.get("/api/v1/social/content/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "platform" in exported.text
    assert "body text" in exported.text
