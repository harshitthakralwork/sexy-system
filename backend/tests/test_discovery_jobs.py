"""Phase 3: a discovery job that runs, persists and reports what really happened.

Every test drives the HTTP API and then reads the database, because the point of
this phase is that discovered businesses stop living in memory. Stub adapters
stand in for the network only — the pipeline, the store and the job rows are real.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import session_scope
from app.modules.discovery import job_service, runner
from app.modules.discovery.adapters.base import (
    AccessDeniedError,
    AdapterCapabilities,
    DiscoveredItem,
    HealthResult,
)
from app.modules.discovery.models import DiscoveryJob, SourceRecord
from tests.conftest import Session

CAPABILITIES = AdapterCapabilities(
    adapter_key="overpass",
    name="OpenStreetMap (Overpass API)",
    slug="overpass",
    category="geographic",
    supported_query_types=("category", "radius"),
    supported_filters=("radius_km",),
    available_fields=("name", "latitude", "longitude"),
    geographic_coverage="Fixture coverage note, standing in for the real source.",
)


class StubAdapter:
    """Returns prepared items, or fails on purpose when asked to."""

    def __init__(self, items: list[DiscoveredItem] | None = None, error: Exception | None = None):
        self._items = items or []
        self._error = error
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return CAPABILITIES

    async def validate_config(self, config: dict[str, Any]) -> None:
        del config

    async def health_check(self) -> HealthResult:
        return HealthResult(status="working")

    async def discover(self, query: Any) -> list[DiscoveredItem]:
        del query
        self.requests_made += 1
        if self._error is not None:
            raise self._error
        return list(self._items)

    async def aclose(self) -> None:
        return None


def item(domain: str, name: str) -> DiscoveredItem:
    """A distinct business. The phone is unique per fixture so two items are
    never merged as duplicates of each other by accident."""
    phone = f"+91 9{str(uuid.uuid4().int % 10**9).zfill(9)}"
    return DiscoveredItem(
        external_id=f"node-{domain}",
        source_url=f"https://{domain}/",
        title_hint=name,
        raw_data={
            "name": name,
            "website": f"https://{domain}",
            "city": "Bengaluru",
            "phone": phone,
        },
    )


def unidentified() -> DiscoveredItem:
    """A record with no name and no domain: real noise from a real source."""
    return DiscoveredItem(
        external_id="node-junk",
        source_url=None,
        raw_data={"description": "something was mentioned here"},
    )


def unique_domain() -> str:
    return f"stub-{uuid.uuid4().hex[:8]}.dev"


@pytest.fixture(autouse=True)
def _inline_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jobs must run inline regardless of what the operator's `.env` says.

    Without this, a machine configured for Celery would pass these tests having
    proved only that a job can be queued.
    """
    monkeypatch.setenv("SPARKX_RUN_JOBS_SYNCHRONOUSLY", "true")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()


@pytest.fixture()
def stub_adapters(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[StubAdapter]], None]:
    """Replace adapter construction with the given stubs."""

    def install(adapters: list[StubAdapter]) -> None:
        built = [(adapter.capabilities.slug, adapter) for adapter in adapters]

        def build(settings: Any, slugs: Any) -> list[tuple[str, Any]]:
            del settings, slugs
            return built

        monkeypatch.setattr(runner, "build_adapters", build)

    return install


def create_job(account: Session, payload: dict[str, Any]) -> dict[str, Any]:
    response = account.api.post(
        "/api/v1/discovery/jobs",
        json=payload,
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def read_job(job_id: uuid.UUID) -> dict[str, Any]:
    """Re-read a job straight from the database, past any response caching."""

    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, job_id)
            assert job is not None
            return {
                "status": job.status,
                "total": job.total_records,
                "processed": job.processed_records,
                "failed": job.failed_records,
                "progress": float(job.progress_percent),
                "report": job.report,
                "error_details": job.error_details,
            }

    return asyncio.run(load())


def count_job_records(job_id: uuid.UUID) -> int:
    async def load() -> int:
        async with session_scope() as session:
            rows = await session.scalars(
                select(SourceRecord.id).where(SourceRecord.job_id == job_id)
            )
            return len(rows.all())

    return asyncio.run(load())


def test_job_runs_and_persists_businesses(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    domain = unique_domain()
    stub_adapters([StubAdapter(items=[item(domain, "Cafe Aroma"), unidentified()])])

    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})
    job = read_job(uuid.UUID(created["id"]))

    assert job["status"] == "completed"
    assert job["total"] == 2
    assert job["failed"] == 1
    assert job["report"]["counters"]["stored_new"] == 1
    assert job["report"]["skipped_provenance"] == 0

    listed = session_account.api.get("/api/v1/businesses")
    assert listed.status_code == 200
    assert "Cafe Aroma" in [row["name"] for row in listed.json()["items"]]


def test_provenance_rows_are_attributed_to_the_job(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    domain = unique_domain()
    stub_adapters([StubAdapter(items=[item(domain, "Filter Coffee House")])])

    created = create_job(session_account, {"keywords": ["coffee"], "sources": ["overpass"]})
    job_id = uuid.UUID(created["id"])

    assert count_job_records(job_id) == 1

    businesses = session_account.api.get("/api/v1/businesses").json()["items"]
    row = next(entry for entry in businesses if entry["name"] == "Filter Coffee House")
    detail = session_account.api.get(f"/api/v1/businesses/{row['id']}")
    assert detail.status_code == 200
    assert "overpass" in detail.json()["source_slugs"]


def test_progress_counts_only_records_that_reached_the_end(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters(
        [
            StubAdapter(
                items=[
                    item(unique_domain(), "One"),
                    item(unique_domain(), "Two"),
                    unidentified(),
                ]
            )
        ]
    )

    created = create_job(session_account, {"keywords": ["shop"], "sources": ["overpass"]})
    job = read_job(uuid.UUID(created["id"]))

    assert job["processed"] == 3
    assert job["progress"] == 100.0


def test_source_failure_is_reported_rather_than_hidden(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(error=AccessDeniedError("429 from the endpoint"))])

    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})
    job = read_job(uuid.UUID(created["id"]))

    assert job["status"] == "failed"
    assert "access_denied" in str(job["error_details"])


def test_one_dead_source_does_not_erase_the_other_s_results(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    domain = unique_domain()
    stub_adapters(
        [
            StubAdapter(error=AccessDeniedError("instance offline")),
            StubAdapter(items=[item(domain, "Still Found It")]),
        ]
    )

    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})
    job = read_job(uuid.UUID(created["id"]))

    assert job["status"] == "completed"
    assert job["report"]["stored_new"] == 1
    assert job["report"]["sources"][0]["failed"] is True
    assert "partial_failure" in job["error_details"]


def test_a_cancelled_job_stops_before_storing_anything(
    make_account: Callable[[], Session],
    stub_adapters: Callable[[list[StubAdapter]], None],
) -> None:
    """What a worker picking up a cancelled job must do: notice, and stop.

    The job row is created without going through the API so it can still be in
    `queued` when the runner starts — inline dispatch would have finished it
    before a cancellation could be observed.
    """
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Never Stored")])])
    account = make_account()
    owner = uuid.UUID(account.user_id)

    async def scenario() -> tuple[str, int]:
        async with session_scope() as session:
            job = await job_service.create_job(
                session,
                owner_user_id=owner,
                config={"keywords": ["cafe"], "sources": ["overpass"]},
                correlation_id=None,
            )
            job_id = job.id

        async with session_scope() as session:
            queued = await session.get(DiscoveryJob, job_id)
            assert queued is not None
            queued.status = "cancelled"
            await session.commit()

        outcome = await runner.execute(job_id)

        async with session_scope() as session:
            records = await session.scalars(
                select(SourceRecord.id).where(SourceRecord.job_id == job_id)
            )
            return outcome, len(records.all())

    outcome, record_count = asyncio.run(scenario())

    assert outcome == "cancelled"
    assert record_count == 0


def test_cancelling_a_finished_job_is_refused(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Done Deal")])])
    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})

    response = session_account.api.post(
        f"/api/v1/discovery/jobs/{created['id']}/cancel",
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"


def test_another_user_cannot_see_or_cancel_the_job(
    make_account: Callable[[], Session],
    stub_adapters: Callable[[list[StubAdapter]], None],
) -> None:
    owner = make_account()
    intruder = make_account()
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Private Find")])])

    created = create_job(owner, {"keywords": ["cafe"], "sources": ["overpass"]})
    job_id = created["id"]

    headers = {**intruder.csrf_headers(), "Origin": "http://localhost:3000"}
    assert intruder.api.get(f"/api/v1/discovery/jobs/{job_id}").status_code == 404
    cancelled = intruder.api.post(f"/api/v1/discovery/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.status_code == 404
    assert intruder.api.get(f"/api/v1/discovery/jobs/{job_id}/logs").status_code == 404

    listing = intruder.api.get("/api/v1/businesses").json()
    assert all(entry["name"] != "Private Find" for entry in listing["items"])


def test_job_listing_only_shows_the_callers_own_jobs(
    make_account: Callable[[], Session],
    stub_adapters: Callable[[list[StubAdapter]], None],
) -> None:
    owner = make_account()
    other = make_account()
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Mine")])])

    created = create_job(owner, {"keywords": ["cafe"], "sources": ["overpass"]})
    listed = other.api.get("/api/v1/discovery/jobs").json()

    assert created["id"] not in [row["id"] for row in listed["items"]]
    mine = owner.api.get("/api/v1/discovery/jobs").json()
    assert created["id"] in [row["id"] for row in mine["items"]]


def test_state_changes_require_the_csrf_token(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(items=[])])
    response = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"keywords": ["cafe"], "sources": ["overpass"]},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 403


def test_unknown_source_is_refused_before_it_can_fail(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"keywords": ["cafe"], "sources": ["google-maps"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 422
    assert "google-maps" in str(response.json())


def test_a_query_with_nothing_to_search_for_is_refused(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 422

    body = response.json()
    assert body["error"]["code"] == "validation_failed"
    # A model_validator failure carries the original ValueError in `ctx`, which
    # is not JSON. Left in, every such rejection would answer 500 instead of 422.
    for entry in body["error"]["details"]["errors"]:
        assert "ctx" not in entry
    assert any(entry["loc"] == ["body"] for entry in body["error"]["details"]["errors"])


def test_no_broker_leaves_the_job_blocked_not_lost(
    session_account: Session,
    stub_adapters: Callable[[list[StubAdapter]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued job with nowhere to go must say so, not vanish quietly."""
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Queued Forever")])])

    class UnreachableDispatcher:
        def submit(self, task_name: str, payload: dict[str, Any]) -> str:
            del task_name, payload
            raise ConnectionError("no broker at redis://localhost:6379")

    monkeypatch.setattr(runner, "get_dispatcher", lambda: UnreachableDispatcher())

    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})
    job = read_job(uuid.UUID(created["id"]))

    assert job["status"] == "blocked"
    assert "RUN_JOBS_SYNCHRONOUSLY" in job["error_details"]["reason"]


def test_logs_record_what_the_job_saw(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(error=AccessDeniedError("endpoint refused"))])
    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})

    logs = session_account.api.get(f"/api/v1/discovery/jobs/{created['id']}/logs").json()
    messages = " ".join(entry["message"] for entry in logs)

    assert "Started with sources" in messages
    assert any(entry["metadata"].get("classification") == "access_denied" for entry in logs)
