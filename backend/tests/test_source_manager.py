"""Master plan #28: Source Manager.

The registry tables already existed but nothing read or changed them, so the screen
had no power over anything. These tests prove the three things that make it a manager
rather than a listing: the switch is honoured by the code that runs jobs, the health
and usage figures are recorded from real runs and real probes, and per-account
configuration is validated by the adapter that has to live with it.

Only the network is faked. The orchestrator, the job rows, the registry and
PostgreSQL are the real ones.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.database import session_scope
from app.modules.discovery import runner
from app.modules.discovery.adapters.base import (
    AdapterCapabilities,
    AdapterError,
    HealthResult,
)
from app.modules.discovery.models import DiscoveryJob
from app.modules.social import tracks
from app.modules.social.adapters import SocialResult
from app.modules.social.models import SocialDiscoveryRun
from app.modules.social.schemas import TrackCreateIn
from app.modules.sources.models import (
    Source,
    SourceConfiguration,
)
from tests.conftest import Session
from tests.discovery_doubles import StubAdapter, item, unique_domain

DEMAND_TEXT = "Looking for a web development agency to rebuild our site"


def _delete_source_row(slug: str) -> None:
    """Remove a registry row this test created.

    Only ever used for a synthetic slug with no provenance pointing at it; deleting
    a real provider's row would cascade to the records that cite it.
    """

    async def run() -> None:
        async with session_scope() as session:
            await session.execute(delete(Source).where(Source.slug == slug))

    asyncio.run(run())


def _source_row(slug: str) -> dict[str, Any]:
    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.scalar(select(Source).where(Source.slug == slug))
            assert row is not None, f"{slug} was never registered"
            return {
                "health_status": row.health_status,
                "last_error": row.last_error,
                "is_enabled": row.is_enabled,
            }

    return asyncio.run(load())


def _config_row(owner_id: str, slug: str) -> dict[str, Any] | None:
    async def load() -> dict[str, Any] | None:
        owner = uuid.UUID(owner_id)
        async with session_scope() as session:
            row = await session.scalar(
                select(SourceConfiguration)
                .join(Source, Source.id == SourceConfiguration.source_id)
                .where(Source.slug == slug, SourceConfiguration.owner_user_id == owner)
            )
            if row is None:
                return None
            return {
                "is_enabled": row.is_enabled,
                "configuration": row.configuration,
                "secret_reference": row.secret_reference,
            }

    return asyncio.run(load())


def _find_source(account: Session, slug: str) -> dict[str, Any]:
    body = account.api.get("/api/v1/sources").json()
    for group in body["groups"]:
        for row in group["items"]:
            if row["slug"] == slug:
                return row
    raise AssertionError(f"{slug} is not listed in the Source Manager")


# --- Registry ---------------------------------------------------------------


def test_registry_lists_every_runnable_source_once(session_account: Session) -> None:
    """Every adapter this build can actually run appears, and SearXNG appears once.

    One provider serving both discovery and social tracks must not look like two
    independent sources: its health and its usage would be counted twice.
    """
    body = session_account.api.get("/api/v1/sources").json()
    slugs = [row["slug"] for group in body["groups"] for row in group["items"]]

    assert len(slugs) == len(set(slugs)), "a provider was registered twice"
    assert slugs.count("searxng") == 1
    for expected in ("overpass", "searxng", "reddit", "hackernews", "rss", "mastodon"):
        assert expected in slugs, f"{expected} is missing from the registry"
    assert body["total"] == len(slugs)

    categories = {group["category"] for group in body["groups"]}
    assert {"geographic", "search", "social"} <= categories


def test_source_rows_carry_their_own_limitations(session_account: Session) -> None:
    """The descriptions come from the adapter, not from a hand-written list.

    Overpass is the proof that matters: its whole point is that missing businesses
    are an OSM mapping gap, and the manager has to say so.
    """
    overpass = _find_source(session_account, "overpass")
    assert "patchy" in overpass["coverage"]["geographic_coverage"]
    assert "throttles by IP" in overpass["limitations"]["rate_limit_notes"]
    assert "OpenDatabase" in overpass["limitations"]["terms_notes"]
    assert overpass["globally_enabled"] is True
    assert overpass["limitations"]["max_results_per_query"] == 1000


def test_a_source_that_has_never_been_probed_claims_no_health(
    session_account: Session,
) -> None:
    """A row with no runs and no probes must show nothing, not a reassuring badge.

    Inserted directly because this is the shape of the table a first registration
    leaves behind; the job API only accepts providers it can actually build.
    """
    slug = f"watched-{uuid.uuid4().hex[:8]}"

    async def seed() -> None:
        async with session_scope() as session:
            session.add(
                Source(
                    name="Watched Stub Source",
                    slug=slug,
                    category="social",
                    adapter_key="hackernews",
                    description="Registered but never run.",
                    capabilities={"available_fields": ["title"]},
                    limitations={"rate_limit_notes": "One call per run."},
                    coverage={"geographic_coverage": "test"},
                    rate_limit_config={"notes": "One call per run."},
                )
            )

    asyncio.run(seed())

    row = _find_source(session_account, slug)
    assert row["health_status"] == "unknown"
    assert row["last_error"] is None
    assert row["last_check_at"] is None
    assert row["last_check_response_ms"] is None
    assert row["last_successful_run_at"] is None
    assert row["requests_count"] == 0
    assert row["records_returned"] == 0
    assert row["records_accepted"] is None
    assert row["enabled_for_user"] is True

    history = session_account.api.get(f"/api/v1/sources/{slug}/history").json()
    assert history["checks"] == []
    assert history["runs"] == []
    _delete_source_row(slug)


def test_the_manager_repairs_a_row_that_stopped_matching_its_adapter(
    session_account: Session,
) -> None:
    """A registry row is generated from code, so a stale one must not survive.

    The corruption written here is exactly what a first-writer-wins registry leaves
    behind: a name and limitations that no adapter declares any more. The browser
    found a row like this being shown to the operator as if it were the provider.
    """
    from app.core.config import get_settings
    from app.modules.sources import registry

    real_name = registry.adapter_for(get_settings(), "hackernews")[1].capabilities.name

    async def corrupt() -> None:
        async with session_scope() as session:
            row = await session.scalar(select(Source).where(Source.slug == "hackernews"))
            assert row is not None
            row.name = "Fake hackernews"
            row.limitations = {"rate_limit_notes": "", "terms_notes": ""}
            row.coverage = {}

    asyncio.run(corrupt())

    listed = _find_source(session_account, "hackernews")
    assert listed["name"] == real_name
    assert "Algolia" in listed["limitations"]["rate_limit_notes"]
    assert listed["coverage"]["geographic_coverage"]

    # Nothing else about the row was disturbed by the repair.
    assert listed["enabled_for_user"] is True


def test_unknown_source_is_404(session_account: Session) -> None:
    assert session_account.api.get("/api/v1/sources/never-invented").status_code == 404
    assert session_account.api.get("/api/v1/sources/never-invented/history").status_code == 404
    assert (
        session_account.api.post(
            "/api/v1/sources/never-invented/disable", headers=session_account.csrf_headers()
        ).status_code
        == 404
    )


# --- Enable / disable -------------------------------------------------------


def test_disabling_is_per_account(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    other = make_account()
    disabled = session_account.api.post(
        "/api/v1/sources/overpass/disable", headers=session_account.csrf_headers()
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled_for_user"] is False

    assert _find_source(session_account, "overpass")["enabled_for_user"] is False
    # The registry row is shared; the choice is not.
    assert _find_source(other, "overpass")["enabled_for_user"] is True
    assert _source_row("overpass")["is_enabled"] is True

    re_enabled = session_account.api.post(
        "/api/v1/sources/overpass/enable", headers=session_account.csrf_headers()
    )
    assert re_enabled.status_code == 200
    assert _find_source(session_account, "overpass")["enabled_for_user"] is True


@pytest.mark.parametrize(
    "path",
    ["/api/v1/sources/overpass/disable", "/api/v1/sources/overpass/enable"],
)
def test_source_state_changes_require_csrf(session_account: Session, path: str) -> None:
    assert session_account.api.post(path).status_code in (401, 403)


# --- The switch is honoured by the code that runs ---------------------------


@pytest.fixture()
def stub_by_slug(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[StubAdapter]], None]:
    """Install one stub per slug, leaving every other slug to the real factory.

    Two things are being proven at once: the runner must honour the requested slugs
    (a stub it does not declare is an error, not a silent skip), and the Source
    Manager must still be able to build the providers it lists. Delegating the
    unknown slugs keeps the patch from disabling the very registry under test.
    """

    def install(adapters: list[StubAdapter]) -> None:
        mapping = {adapter.capabilities.slug: adapter for adapter in adapters}
        real_build = runner.build_adapters

        def build(settings: Any, slugs: Any) -> list[tuple[str, Any]]:
            known = [slug for slug in slugs if slug in mapping]
            unknown = [slug for slug in slugs if slug not in mapping]
            built = [(slug, mapping[slug]) for slug in known]
            if unknown:
                built.extend(real_build(settings, unknown))
            return built

        monkeypatch.setattr(runner, "build_adapters", build)

    return install


def test_disabled_source_is_skipped_by_a_discovery_job(
    session_account: Session, stub_by_slug: Callable[[list[StubAdapter]], None]
) -> None:
    domain = unique_domain()
    overpass = StubAdapter(items=[item(domain, "Skipped Test Cafe")])
    searxng = StubAdapter(
        items=[item(domain, "Should Never Appear")],
        capabilities=AdapterCapabilities(
            adapter_key="searxng",
            name="SearXNG",
            slug="searxng",
            category="search",
            supported_query_types=("keyword",),
            supported_filters=(),
            available_fields=("title",),
            geographic_coverage="test",
        ),
    )
    stub_by_slug([overpass, searxng])

    session_account.api.post(
        "/api/v1/sources/searxng/disable", headers=session_account.csrf_headers()
    )
    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"keywords": ["cafe"], "sources": ["overpass", "searxng"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text

    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, uuid.UUID(created.json()["id"]))
            assert job is not None
            return {"status": job.status, "report": job.report, "error": job.error_details}

    job = asyncio.run(load())
    assert job["status"] == "completed"
    assert job["report"]["skipped_sources"] == {"searxng": "disabled for your account"}
    assert len(overpass.queries) == 1
    # The disabled provider was never asked a single question.
    assert searxng.queries == []

    names = [row["name"] for row in session_account.api.get("/api/v1/businesses").json()["items"]]
    assert "Skipped Test Cafe" in names
    assert "Should Never Appear" not in names


def test_job_fails_honestly_when_every_source_is_disabled(
    session_account: Session, stub_by_slug: Callable[[list[StubAdapter]], None]
) -> None:
    stub_by_slug([StubAdapter(items=[item(unique_domain(), "Never Stored")])])
    for slug in ("overpass", "searxng"):
        session_account.api.post(
            f"/api/v1/sources/{slug}/disable", headers=session_account.csrf_headers()
        )

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"keywords": ["cafe"], "sources": ["overpass", "searxng"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text

    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, uuid.UUID(created.json()["id"]))
            assert job is not None
            return {"status": job.status, "error": job.error_details}

    job = asyncio.run(load())
    assert job["status"] == "failed"
    assert "no enabled source left" in str(job["error"])
    assert session_account.api.get("/api/v1/businesses").json()["items"] == []


def test_a_run_records_usage_for_the_source_it_used(
    session_account: Session, stub_by_slug: Callable[[list[StubAdapter]], None]
) -> None:
    stub_by_slug([StubAdapter(items=[item(unique_domain(), "Counted Cafe")])])
    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"keywords": ["cafe"], "sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text

    row = _find_source(session_account, "overpass")
    assert row["requests_count"] >= 1
    assert row["records_returned"] >= 1
    assert row["last_successful_run_at"] is not None
    # The pipeline counts stored rows per job, not per source, so this stays null
    # rather than borrowing a number it never observed.
    assert row["records_accepted"] is None

    history = session_account.api.get("/api/v1/sources/overpass/history").json()
    assert history["runs"], "the run left no per-source record"


# --- Test connection --------------------------------------------------------


class ProbingAdapter:
    """A social connector whose health answer the test decides."""

    def __init__(self, key: str, *, outcome: HealthResult | Exception) -> None:
        self.key = key
        self._outcome = outcome

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key=self.key,
            name=self.key.title(),
            slug=self.key,
            category="social",
            supported_query_types=("keyword",),
            supported_filters=(),
            available_fields=("title",),
            geographic_coverage="test",
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        return None

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        return []

    async def health_check(self) -> HealthResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def fake_social_sources(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, Any]], None]:
    def install(outcomes: dict[str, Any]) -> None:
        from app.modules.social import service as social_service

        def build(settings: Any, key: str) -> ProbingAdapter:
            del settings
            return ProbingAdapter(key, outcome=outcomes.get(key, HealthResult(status="unknown")))

        monkeypatch.setattr(social_service, "_build_adapter", build)

    return install


def test_test_connection_records_a_real_probe(
    session_account: Session, fake_social_sources: Callable[[dict[str, Any]], None]
) -> None:
    fake_social_sources({"hackernews": HealthResult(status="working", response_time_ms=142)})
    response = session_account.api.post(
        "/api/v1/sources/hackernews/test", headers=session_account.csrf_headers()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "working"
    assert body["response_time_ms"] == 142

    assert _source_row("hackernews")["health_status"] == "working"
    listed = _find_source(session_account, "hackernews")
    assert listed["last_check_response_ms"] == 142
    history = session_account.api.get("/api/v1/sources/hackernews/history").json()
    # Newest first: earlier probes from other runs are still on this shared row.
    assert history["checks"][0]["status"] == "working"
    assert history["checks"][0]["response_time_ms"] == 142


def test_a_refused_provider_is_recorded_as_failed_not_blank(
    session_account: Session, fake_social_sources: Callable[[dict[str, Any]], None]
) -> None:
    fake_social_sources(
        {"reddit": AdapterError("403 unauthenticated JSON blocked", classification="access_denied")}
    )
    response = session_account.api.post(
        "/api/v1/sources/reddit/test", headers=session_account.csrf_headers()
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "403" in str(response.json()["detail"])

    row = _source_row("reddit")
    assert row["health_status"] == "failed"
    assert "403" in str(row["last_error"])


def test_rss_health_stays_unknown_until_a_feed_is_actually_run(
    session_account: Session,
) -> None:
    """The real connector's own answer, unedited.

    RSS health is per-feed, so a provider-wide probe must report `unknown` rather
    than a green badge invented from nothing.
    """
    response = session_account.api.post(
        "/api/v1/sources/rss/test", headers=session_account.csrf_headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unknown"
    assert response.json()["detail"]
    assert _source_row("rss")["health_status"] == "unknown"


# --- Configure --------------------------------------------------------------


def test_rss_feeds_configured_here_are_validated_by_the_adapter(
    session_account: Session,
) -> None:
    accepted = session_account.api.put(
        "/api/v1/sources/rss/config",
        json={"feed_urls": ["https://example.com/feed.xml"]},
        headers=session_account.csrf_headers(),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["configuration"] == {"feed_urls": ["https://example.com/feed.xml"]}

    # The SSRF guard the connectors already use applies at configuration time,
    # so a private target is refused here rather than at run time.
    refused = session_account.api.put(
        "/api/v1/sources/rss/config",
        json={"feed_urls": ["http://127.0.0.1:9/admin.rss"]},
        headers=session_account.csrf_headers(),
    )
    assert refused.status_code == 422
    assert "SSRF" in str(refused.json())

    bad_scheme = session_account.api.put(
        "/api/v1/sources/rss/config",
        json={"feed_urls": ["ftp://example.com/feed.xml"]},
        headers=session_account.csrf_headers(),
    )
    assert bad_scheme.status_code == 422


def test_feed_urls_are_refused_for_a_source_that_cannot_use_them(
    session_account: Session,
) -> None:
    response = session_account.api.put(
        "/api/v1/sources/overpass/config",
        json={"feed_urls": ["https://example.com/feed.xml"]},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422
    assert "RSS" in str(response.json())


def test_configuration_is_per_account_and_stores_no_secret_value(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    other = make_account()
    session_account.api.put(
        "/api/v1/sources/rss/config",
        json={"feed_urls": ["https://example.com/demand.xml"], "note": "tech feeds"},
        headers=session_account.csrf_headers(),
    )
    assert _config_row(session_account.user_id, "rss") == {
        "is_enabled": True,
        "configuration": {"feed_urls": ["https://example.com/demand.xml"], "note": "tech feeds"},
        "secret_reference": None,
    }
    assert _config_row(other.user_id, "rss") is None


# --- Track enforcement ------------------------------------------------------


class TrackAdapter:
    def __init__(self, key: str, captured: list[dict[str, Any]]) -> None:
        self.key = key
        self.captured = captured
        self.requests_made = 1

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key=self.key,
            name=self.key.title(),
            slug=self.key,
            category="social",
            supported_query_types=("keyword",),
            supported_filters=(),
            available_fields=("title",),
            geographic_coverage="test",
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        return None

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        self.captured.append(config)
        return [
            SocialResult(
                external_id=f"{self.key}-1",
                content_url=f"https://example.com/{self.key}",
                content_type="post",
                content_text=DEMAND_TEXT,
                published_at=None,
                raw_data={},
            )
        ]

    async def health_check(self) -> HealthResult:
        return HealthResult(status="working")

    async def aclose(self) -> None:
        return None


def _run_track(owner: uuid.UUID, platforms: list[str], source_config: dict | None = None) -> dict:
    async def scenario() -> dict[str, Any]:
        async with session_scope() as session:
            data = TrackCreateIn(
                name="Manager track",
                track_type="demand",
                keywords=["web development agency"],
                platforms=platforms,
                source_config=source_config or {},
            )
            track = await tracks.create_track(session, owner, data)
            run = SocialDiscoveryRun(
                owner_user_id=owner, track_id=track.id, status="pending", trigger_type="manual"
            )
            session.add(run)
            await session.flush()
            run_id = run.id
        status = await tracks.execute_track_run(run_id)
        async with session_scope() as session:
            row = await session.get(SocialDiscoveryRun, run_id)
            assert row is not None
            return {
                "status": status,
                "stored_new": row.stored_new,
                "results_returned": row.results_returned,
                "error_summary": row.error_summary,
            }

    return asyncio.run(scenario())


def test_track_skips_a_source_disabled_for_the_account(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tracks, "_build_adapter", lambda settings, key: TrackAdapter(key, captured)
    )
    session_account.api.put(
        "/api/v1/sources/hackernews/config",
        json={},
        headers=session_account.csrf_headers(),
    )
    session_account.api.post(
        "/api/v1/sources/hackernews/disable", headers=session_account.csrf_headers()
    )

    record = _run_track(uuid.UUID(session_account.user_id), ["hackernews"])
    assert record["status"] == "failed"
    assert "disabled for your account" in str(record["error_summary"])
    assert captured == []


def test_track_uses_feeds_configured_in_the_source_manager(
    session_account: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configure is only real if the runner reads it back."""
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(tracks, "_build_adapter", lambda settings, key: TrackAdapter(key, captured))

    session_account.api.put(
        "/api/v1/sources/rss/config",
        json={"feed_urls": ["https://example.com/demand.xml"]},
        headers=session_account.csrf_headers(),
    )
    initial_accepted = _find_source(session_account, "rss")["records_accepted"]
    # The track itself names no feeds; the account's setting supplies them.
    record = _run_track(uuid.UUID(session_account.user_id), ["rss"])

    assert record["status"] == "completed", record
    assert captured == [{"feed_urls": ["https://example.com/demand.xml"]}]
    row = _find_source(session_account, "rss")
    assert row["records_accepted"] - initial_accepted == record["stored_new"]
    assert row["health_status"] == "working"
