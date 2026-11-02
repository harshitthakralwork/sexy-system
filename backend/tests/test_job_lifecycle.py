"""Background-execution lifecycle: claim, retry, duplicate delivery, recovery.

These are the guarantees Phase 1 exists to provide — a job runs exactly once per
submission, a failed job can be retried, and a worker that dies mid-run leaves a
recoverable row rather than one stuck in `running` forever.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.modules.discovery import job_service, runner
from app.modules.discovery.adapters.base import AccessDeniedError
from app.modules.discovery.models import DiscoveryJob, SourceRecord
from tests.conftest import Session
from tests.discovery_doubles import StubAdapter, item, unique_domain


def create_job(account: Session, payload: dict[str, Any]) -> dict[str, Any]:
    response = account.api.post(
        "/api/v1/discovery/jobs",
        json=payload,
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def read_job(job_id: uuid.UUID) -> dict[str, Any]:
    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, job_id)
            assert job is not None
            return {
                "status": job.status,
                "retry_count": job.retry_count,
                "report": job.report,
                "error_details": job.error_details,
            }

    return asyncio.run(load())


def test_duplicate_execution_of_a_completed_job_is_a_noop(
    make_account: Callable[[], Session],
    stub_adapters: Callable[[list[StubAdapter]], None],
) -> None:
    """The same job delivered twice must not be swept twice."""
    domain = unique_domain()
    stub_adapters([StubAdapter(items=[item(domain, "Once Only")])])
    account = make_account()
    owner = uuid.UUID(account.user_id)

    async def scenario() -> tuple[str, str, int]:
        async with session_scope() as session:
            job = await job_service.create_job(
                session,
                owner_user_id=owner,
                config={"keywords": ["cafe"], "sources": ["overpass"]},
                correlation_id=None,
            )
            job_id = job.id

        first = await runner.execute(job_id)
        second = await runner.execute(job_id)

        async with session_scope() as session:
            records = await session.scalars(
                select(SourceRecord.id).where(SourceRecord.job_id == job_id)
            )
            return first, second, len(records.all())

    first, second, count = asyncio.run(scenario())

    assert first == "completed"
    assert second == "completed"
    assert count == 1


def test_claim_hands_a_job_to_exactly_one_worker(make_account: Callable[[], Session]) -> None:
    account = make_account()
    owner = uuid.UUID(account.user_id)

    async def scenario() -> tuple[DiscoveryJob | None, DiscoveryJob | None]:
        async with session_scope() as session:
            job = await job_service.create_job(
                session,
                owner_user_id=owner,
                config={"keywords": ["cafe"], "sources": ["overpass"]},
                correlation_id=None,
            )
            job_id = job.id

        async with session_scope() as session:
            first = await job_service.claim_job(session, job_id)
            second = await job_service.claim_job(session, job_id)
            return first, second

    first, second = asyncio.run(scenario())

    assert first is not None and first.status == "running"
    assert second is None


def test_failed_job_can_be_retried_and_runs_again(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(error=AccessDeniedError("instance down"))])
    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})
    job_id = uuid.UUID(created["id"])

    assert read_job(job_id)["status"] == "failed"

    stub_adapters([StubAdapter(items=[item(unique_domain(), "Recovered Cafe")])])
    retried = session_account.api.post(
        f"/api/v1/discovery/jobs/{job_id}/retry",
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["retry_count"] == 1

    job = read_job(job_id)
    assert job["status"] == "completed"
    assert job["report"]["totals"]["stored_new"] == 1


def test_retrying_a_completed_job_is_refused(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Done Deal")])])
    created = create_job(session_account, {"keywords": ["cafe"], "sources": ["overpass"]})

    response = session_account.api.post(
        f"/api/v1/discovery/jobs/{created['id']}/retry",
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_job_state"


def test_another_user_cannot_retry_the_job(
    make_account: Callable[[], Session],
    stub_adapters: Callable[[list[StubAdapter]], None],
) -> None:
    owner = make_account()
    intruder = make_account()
    stub_adapters([StubAdapter(error=AccessDeniedError("down"))])
    created = create_job(owner, {"keywords": ["cafe"], "sources": ["overpass"]})

    response = intruder.api.post(
        f"/api/v1/discovery/jobs/{created['id']}/retry",
        headers={**intruder.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 404


def _make_job_with_status(
    owner: uuid.UUID, *, status: str, started_at: datetime
) -> uuid.UUID:
    async def scenario() -> uuid.UUID:
        async with session_scope() as session:
            job = await job_service.create_job(
                session,
                owner_user_id=owner,
                config={"keywords": ["cafe"], "sources": ["overpass"]},
                correlation_id=None,
            )
            job_id = job.id
        async with session_scope() as session:
            row = await session.get(DiscoveryJob, job_id)
            assert row is not None
            row.status = status
            row.started_at = started_at
            await session.commit()
        return job_id

    return asyncio.run(scenario())


def test_stale_running_job_is_marked_failed(make_account: Callable[[], Session]) -> None:
    account = make_account()
    owner = uuid.UUID(account.user_id)
    job_id = _make_job_with_status(
        owner, status="running", started_at=datetime.now(UTC) - timedelta(hours=7)
    )

    async def scenario() -> tuple[int, str, dict | None]:
        async with session_scope() as session:
            count = await job_service.recover_stale_jobs(session, stale_after_seconds=6 * 3600)
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, job_id)
            assert job is not None
            return count, job.status, job.error_details

    count, status, details = asyncio.run(scenario())

    assert count == 1
    assert status == "failed"
    assert details is not None and details.get("stale") is True


def test_recent_running_job_is_left_alone(make_account: Callable[[], Session]) -> None:
    account = make_account()
    owner = uuid.UUID(account.user_id)
    job_id = _make_job_with_status(
        owner, status="running", started_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    async def scenario() -> tuple[int, str]:
        async with session_scope() as session:
            count = await job_service.recover_stale_jobs(session, stale_after_seconds=6 * 3600)
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, job_id)
            assert job is not None
            return count, job.status

    count, status = asyncio.run(scenario())

    assert count == 0
    assert status == "running"
