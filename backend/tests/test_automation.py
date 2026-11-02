"""Phase 5: automation engine — workflows, schedules, executions, approvals.

Every test drives the HTTP API against real persistence, and the run-now path
exercises the synchronous dispatcher so an execution is proven to complete, not
just to be queued. The cron parser is tested as a pure function because it is the
one piece whose correctness is a matter of arithmetic, not of I/O.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.database import session_scope
from app.core.exceptions import ValidationFailedError
from app.modules.automation import service
from app.modules.businesses.models import Business
from tests.conftest import Session

SHORTLIST_STEP = {"key": "shortlist", "type": "shortlist", "config": {"only_qualified": False}}
DRAFT_STEP = {"key": "draft", "type": "email_draft", "config": {"service_name": "websites"}}


def _create_workflow(account: Session, *, steps: list[dict] | None = None) -> dict:
    response = account.api.post(
        "/api/v1/workflows",
        json={
            "name": "Qualify and draft",
            "module": "leads",
            "steps": steps if steps is not None else [SHORTLIST_STEP, DRAFT_STEP],
        },
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
                email="owner@sparkcafe.in",
                website_status="available",
                normalized_domain="sparkcafe.in",
                city="Pune",
            )
            db.add(business)
            await db.flush()
            return str(business.id)

    return asyncio.run(run())


def _run_workflow(
    account: Session, workflow_id: str, *, business_ids: list[str] | None = None
) -> str:
    response = account.api.post(
        f"/api/v1/workflows/{workflow_id}/run",
        json={"input_data": {"business_ids": business_ids or []}},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["execution_id"]


def _read_execution(account: Session, execution_id: str) -> dict:
    response = account.api.get(f"/api/v1/workflows/executions/{execution_id}")
    assert response.status_code == 200, response.text
    return response.json()


# --- Cron parsing (pure functions, no database) -----------------------------


def test_cron_every_minute_star() -> None:
    after = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    nxt = service.next_cron("* * * * *", after)
    assert nxt == datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC)


def test_cron_daily_at_midnight() -> None:
    after = datetime(2026, 1, 1, 12, 30, 0, tzinfo=UTC)
    nxt = service.next_cron("0 0 * * *", after)
    assert nxt == datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def test_cron_step_values() -> None:
    after = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    nxt = service.next_cron("*/15 * * * *", after)
    assert nxt == datetime(2026, 1, 1, 12, 15, 0, tzinfo=UTC)


def test_cron_specific_weekday() -> None:
    # 2026-01-01 is a Thursday. "0 9 * * 1" is Monday 09:00.
    after = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    nxt = service.next_cron("0 9 * * 1", after)
    assert nxt == datetime(2026, 1, 5, 9, 0, 0, tzinfo=UTC)


def test_cron_out_of_range_field_raises() -> None:
    with pytest.raises(ValueError):
        service.next_cron("60 * * * *", datetime.now(UTC))


def test_cron_impossible_date_returns_none() -> None:
    # Feb 31 never occurs; the scan must terminate rather than loop forever.
    assert service.next_cron("0 0 31 2 *", datetime(2026, 1, 1, tzinfo=UTC)) is None


def test_compute_next_run_interval() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    now = datetime(2026, 1, 1, 2, 5, 0, tzinfo=UTC)
    nxt = service.compute_next_run(
        {"interval_seconds": 3600}, start_at=start, last_run_at=None, now=now
    )
    assert nxt == datetime(2026, 1, 1, 3, 0, 0, tzinfo=UTC)


def test_compute_next_run_unknown_timezone() -> None:
    with pytest.raises(ValidationFailedError):
        service.compute_next_run(
            {"interval_seconds": 3600},
            start_at=datetime.now(UTC),
            last_run_at=None,
            now=datetime.now(UTC),
            timezone="Not/AZone",
        )


# --- Workflow CRUD ----------------------------------------------------------


def test_workflow_crud_and_version_bump(session_account: Session) -> None:
    created = _create_workflow(session_account)
    assert created["status"] == "draft"
    assert created["version"] == 1
    assert created["workflow_definition"]["steps"][0]["type"] == "shortlist"

    listed = session_account.api.get("/api/v1/workflows")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = session_account.api.patch(
        f"/api/v1/workflows/{created['id']}",
        json={"steps": [SHORTLIST_STEP, DRAFT_STEP, {"key": "send", "type": "send"}]},
        headers=session_account.csrf_headers(),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] == 2

    renamed = session_account.api.patch(
        f"/api/v1/workflows/{created['id']}",
        json={"name": "Renamed"},
        headers=session_account.csrf_headers(),
    )
    assert renamed.json()["version"] == 2
    assert renamed.json()["name"] == "Renamed"

    deleted = session_account.api.delete(
        f"/api/v1/workflows/{created['id']}",
        headers=session_account.csrf_headers(),
    )
    assert deleted.status_code == 204
    assert session_account.api.get("/api/v1/workflows").json()["total"] == 0


def test_invalid_step_type_rejected(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/workflows",
        json={"name": "Bad", "steps": [{"key": "s", "type": "research"}]},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_duplicate_step_keys_rejected(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/workflows",
        json={
            "name": "Dup",
            "steps": [SHORTLIST_STEP, {"key": "shortlist", "type": "send"}],
        },
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


# --- Schedules --------------------------------------------------------------


def test_schedule_interval_computes_next_run(session_account: Session) -> None:
    workflow = _create_workflow(session_account)
    start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    response = session_account.api.post(
        "/api/v1/workflows/schedules",
        json={
            "workflow_id": workflow["id"],
            "recurrence_config": {"interval_seconds": 3600},
            "start_at": start,
        },
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["next_run_at"] is not None
    assert datetime.fromisoformat(body["next_run_at"]) > datetime.fromisoformat(start)


def test_schedule_requires_exactly_one_recurrence(session_account: Session) -> None:
    workflow = _create_workflow(session_account)
    response = session_account.api.post(
        "/api/v1/workflows/schedules",
        json={
            "workflow_id": workflow["id"],
            "recurrence_config": {"interval_seconds": 3600, "cron": "* * * * *"},
            "start_at": datetime.now(UTC).isoformat(),
        },
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_schedule_unknown_timezone_rejected(session_account: Session) -> None:
    workflow = _create_workflow(session_account)
    response = session_account.api.post(
        "/api/v1/workflows/schedules",
        json={
            "workflow_id": workflow["id"],
            "recurrence_config": {"cron": "0 9 * * *"},
            "timezone": "Not/AZone",
            "start_at": datetime.now(UTC).isoformat(),
        },
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


# --- Run-now execution ------------------------------------------------------


def test_run_workflow_with_empty_business_ids_completes(session_account: Session) -> None:
    workflow = _create_workflow(
        session_account,
        steps=[
            {"key": "q", "type": "qualify", "config": {"service_id": str(uuid.uuid4())}},
            SHORTLIST_STEP,
        ],
    )
    execution_id = _run_workflow(session_account, workflow["id"])
    execution = _read_execution(session_account, execution_id)
    assert execution["status"] == "completed", execution
    assert {step["step_key"] for step in execution["steps"]} == {"q", "shortlist"}
    assert all(step["status"] == "completed" for step in execution["steps"])


def test_run_workflow_drafts_email_and_gates_on_approval(session_account: Session) -> None:
    workflow = _create_workflow(session_account)
    business_id = _insert_business(session_account.user_id)

    execution_id = _run_workflow(session_account, workflow["id"], business_ids=[business_id])
    execution = _read_execution(session_account, execution_id)
    assert execution["status"] == "completed", execution

    messages = session_account.api.get("/api/v1/email/messages")
    assert messages.status_code == 200
    body = messages.json()
    assert body["total"] == 1
    message = body["items"][0]
    assert message["recipient_email"] == "owner@sparkcafe.in"
    assert message["status"] == "pending_approval"
    assert message["business_id"] == business_id
    assert "sparkcafe.in" in message["body"]

    approvals = session_account.api.get("/api/v1/workflows/approvals")
    assert approvals.json()["total"] == 1
    approval = approvals.json()["items"][0]
    assert approval["status"] == "pending"
    assert approval["original_content"]["message_id"] == message["id"]


def test_archived_workflow_cannot_run(session_account: Session) -> None:
    workflow = _create_workflow(session_account)
    archived = session_account.api.patch(
        f"/api/v1/workflows/{workflow['id']}",
        json={"status": "archived"},
        headers=session_account.csrf_headers(),
    )
    assert archived.status_code == 200
    response = session_account.api.post(
        f"/api/v1/workflows/{workflow['id']}/run",
        json={"input_data": {}},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 409, response.text


# --- Approval review --------------------------------------------------------


def _draft_via_workflow(account: Session) -> tuple[str, str, str]:
    """Run the draft workflow once; return (execution_id, message_id, approval_id)."""
    workflow = _create_workflow(account)
    business_id = _insert_business(account.user_id)
    execution_id = _run_workflow(account, workflow["id"], business_ids=[business_id])
    assert _read_execution(account, execution_id)["status"] == "completed"
    message_id = account.api.get("/api/v1/email/messages").json()["items"][0]["id"]
    approval_id = account.api.get("/api/v1/workflows/approvals").json()["items"][0]["id"]
    return execution_id, message_id, approval_id


def test_approval_review_approves_the_message(session_account: Session) -> None:
    _, message_id, approval_id = _draft_via_workflow(session_account)
    reviewed = session_account.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "approved"},
        headers=session_account.csrf_headers(),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"

    message = session_account.api.get(f"/api/v1/email/messages/{message_id}").json()
    assert message["status"] == "approved"
    assert message["approved_at"] is not None


def test_approval_review_rejects_the_message(session_account: Session) -> None:
    _, message_id, approval_id = _draft_via_workflow(session_account)
    reviewed = session_account.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "rejected"},
        headers=session_account.csrf_headers(),
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "rejected"
    message = session_account.api.get(f"/api/v1/email/messages/{message_id}").json()
    assert message["status"] == "rejected"


def test_approval_cannot_be_reviewed_twice(session_account: Session) -> None:
    _, _, approval_id = _draft_via_workflow(session_account)
    first = session_account.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "approved"},
        headers=session_account.csrf_headers(),
    )
    assert first.status_code == 200
    second = session_account.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "rejected"},
        headers=session_account.csrf_headers(),
    )
    assert second.status_code == 409, second.text


# --- Cross-owner isolation --------------------------------------------------


def test_cross_owner_cannot_see_or_run_workflow(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()
    workflow = _create_workflow(owner)

    assert other.api.get("/api/v1/workflows").json()["total"] == 0
    assert other.api.get(f"/api/v1/workflows/{workflow['id']}").status_code == 404
    run = other.api.post(
        f"/api/v1/workflows/{workflow['id']}/run",
        json={"input_data": {}},
        headers=other.csrf_headers(),
    )
    assert run.status_code == 404, run.text


def test_cross_owner_cannot_review_approval(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()
    _, _, approval_id = _draft_via_workflow(owner)

    assert other.api.get("/api/v1/workflows/approvals").json()["total"] == 0
    review = other.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "approved"},
        headers=other.csrf_headers(),
    )
    assert review.status_code == 404, review.text

    # The owner can still review afterwards.
    owner_review = owner.api.post(
        f"/api/v1/workflows/approvals/{approval_id}/review",
        json={"decision": "approved"},
        headers=owner.csrf_headers(),
    )
    assert owner_review.status_code == 200


def test_cross_owner_schedule_isolation(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()
    workflow = _create_workflow(owner)
    created = owner.api.post(
        "/api/v1/workflows/schedules",
        json={
            "workflow_id": workflow["id"],
            "recurrence_config": {"interval_seconds": 3600},
            "start_at": datetime.now(UTC).isoformat(),
        },
        headers=owner.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    assert other.api.get("/api/v1/workflows/schedules").json()["total"] == 0
    assert other.api.delete(
        f"/api/v1/workflows/schedules/{schedule_id}",
        headers=other.csrf_headers(),
    ).status_code == 404
    assert owner.api.get("/api/v1/workflows/schedules").json()["total"] == 1
