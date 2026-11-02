"""Master plan #27: Analytics & Reports.

Every figure on this surface must be a GROUP BY over the operator's own rows. These
tests seed exact quantities and assert exact counts, so a bucket that silently
double-counts, counts another owner's rows, or invents a default is caught here.
Saved reports are checked the same way: a snapshot must match what the live summary
said at capture time and must not move afterwards.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.discovery.models import DiscoveryJob
from app.modules.social import service as social_service
from app.modules.social.models import SocialContent, SocialPlatform
from app.modules.startups.models import Startup
from tests.conftest import Session

_BUCKET_KEYS = (
    "businesses_by_website_status",
    "businesses_by_lifecycle",
    "crm_by_stage",
    "opportunities_by_status",
    "discovery_jobs_by_status",
    "social_by_classification",
    "social_by_platform",
    "social_by_track_type",
    "startups_by_funding_stage",
)


def _business(
    owner: uuid.UUID, *, name: str, website_status: str, lifecycle_status: str = "active"
) -> Business:
    return Business(
        owner_user_id=owner,
        name=name,
        normalized_name=name.lower(),
        first_discovered_at=datetime.now(UTC),
        website_status=website_status,
        lifecycle_status=lifecycle_status,
    )


def _seed(owner_id: str) -> str:
    """Seed a known quantity on every surface and return one business id."""
    business_id = ""

    async def run() -> None:
        nonlocal business_id
        owner = uuid.UUID(owner_id)
        async with session_scope() as db:
            await social_service.ensure_platforms(db)
            platform = await db.scalar(
                select(SocialPlatform).where(SocialPlatform.slug == "hackernews")
            )
            assert platform is not None
            first = _business(owner, name="Alpha Cafe", website_status="missing")
            second = _business(owner, name="Beta Bakery", website_status="missing")
            third = _business(
                owner, name="Gamma Clinic", website_status="available", lifecycle_status="archived"
            )
            db.add_all([first, second, third])
            await db.flush()
            business_id = str(first.id)

            db.add_all(
                [
                    Startup(
                        owner_user_id=owner,
                        name="Delta Robotics",
                        normalized_name="delta robotics",
                        status="active",
                        funding_stage="seed",
                        first_discovered_at=datetime.now(UTC),
                    ),
                    Startup(
                        owner_user_id=owner,
                        name="Epsilon AI",
                        normalized_name="epsilon ai",
                        status="active",
                        funding_stage="seed",
                        first_discovered_at=datetime.now(UTC),
                    ),
                    Startup(
                        owner_user_id=owner,
                        name="Zeta Foods",
                        normalized_name="zeta foods",
                        status="active",
                        first_discovered_at=datetime.now(UTC),
                    ),
                    DiscoveryJob(owner_user_id=owner, job_type="leads_search", status="completed"),
                    DiscoveryJob(owner_user_id=owner, job_type="leads_search", status="failed"),
                    DiscoveryJob(owner_user_id=owner, job_type="leads_search", status="failed"),
                    SocialContent(
                        platform_id=platform.id,
                        owner_user_id=owner,
                        external_id="alpha-1",
                        content_type="post",
                        title="Looking for a web agency",
                        content_text="we need a website rebuilt",
                        classification="demand",
                        track_type="demand",
                        confidence_score=82,
                    ),
                    SocialContent(
                        platform_id=platform.id,
                        owner_user_id=owner,
                        external_id="alpha-2",
                        content_type="post",
                        title="Alpha Cafe hiring",
                        content_text="Alpha Cafe is hiring baristas",
                        classification="noise",
                        track_type="demand",
                        confidence_score=41,
                    ),
                    SocialContent(
                        platform_id=platform.id,
                        owner_user_id=owner,
                        external_id="alpha-3",
                        content_type="comment",
                        title="Random thread",
                        content_text="unrelated discussion",
                    ),
                ]
            )

    asyncio.run(run())
    return business_id


def _buckets(payload: dict, key: str) -> dict[str, int]:
    return {row["key"]: row["count"] for row in payload[key]}


def test_analytics_is_empty_before_any_data(session_account: Session) -> None:
    """No rows means no numbers — not zeros dressed up as findings."""
    body = session_account.api.get("/api/v1/analytics").json()
    assert body["leads_total"] == 0
    assert all(body[key] == [] for key in _BUCKET_KEYS)


def test_analytics_buckets_count_exactly_the_seeded_rows(session_account: Session) -> None:
    _seed(session_account.user_id)
    body = session_account.api.get("/api/v1/analytics").json()

    assert body["leads_total"] == 3
    assert _buckets(body, "businesses_by_website_status") == {"missing": 2, "available": 1}
    assert _buckets(body, "businesses_by_lifecycle") == {"active": 2, "archived": 1}
    assert _buckets(body, "discovery_jobs_by_status") == {"failed": 2, "completed": 1}
    assert _buckets(body, "startups_by_funding_stage") == {"seed": 2, "unknown": 1}
    assert _buckets(body, "social_by_classification") == {
        "demand": 1,
        "noise": 1,
        "Unclassified": 1,
    }
    assert _buckets(body, "social_by_platform") == {"hackernews": 3}
    assert _buckets(body, "social_by_track_type") == {"demand": 2, "none": 1}

    # Ordering is by count descending, so the biggest bucket leads.
    assert body["discovery_jobs_by_status"][0]["key"] == "failed"
    # Nothing was invented for a surface this owner has never used.
    assert body["crm_by_stage"] == []
    assert body["opportunities_by_status"] == []


def test_soft_deleted_leads_are_excluded_from_every_lead_number(
    session_account: Session,
) -> None:
    """`deleted_at` is what retires a lead, so analytics must stop counting it."""

    async def run() -> None:
        gone = _business(
            uuid.UUID(session_account.user_id), name="Gone Ltd", website_status="unknown"
        )
        gone.deleted_at = datetime.now(UTC)
        async with session_scope() as db:
            db.add(gone)

    asyncio.run(run())
    body = session_account.api.get("/api/v1/analytics").json()
    assert body["leads_total"] == 0
    assert body["businesses_by_website_status"] == []
    assert body["businesses_by_lifecycle"] == []


def test_crm_and_opportunity_buckets_come_from_the_real_flows(
    session_account: Session,
) -> None:
    """Seed through the product's own shortlist and qualify routes."""
    business_id = _seed(session_account.user_id)
    service_id = session_account.api.get("/api/v1/services").json()["items"][0]["id"]

    shortlisted = session_account.api.post(
        f"/api/v1/businesses/{business_id}/shortlist", headers=session_account.csrf_headers()
    )
    assert shortlisted.status_code == 200, shortlisted.text
    qualified = session_account.api.post(
        f"/api/v1/services/{service_id}/qualify/{business_id}",
        headers=session_account.csrf_headers(),
    )
    assert qualified.status_code == 200, qualified.text

    body = session_account.api.get("/api/v1/analytics").json()
    assert _buckets(body, "crm_by_stage") == {"Shortlisted": 1}
    assert _buckets(body, "opportunities_by_status") == {qualified.json()["status"]: 1}


def test_analytics_export_is_the_same_numbers_as_csv(session_account: Session) -> None:
    _seed(session_account.user_id)
    response = session_account.api.get("/api/v1/analytics/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "section,key,count"
    assert "leads_total,,3" in lines
    assert "businesses_by_website_status,missing,2" in lines
    # One row per bucket across every section, nothing invented.
    assert len(lines) == 1 + 1 + sum(
        len(session_account.api.get("/api/v1/analytics").json()[key]) for key in _BUCKET_KEYS
    )


def test_saved_report_snapshots_the_summary_and_does_not_drift(
    session_account: Session,
) -> None:
    _seed(session_account.user_id)
    live = session_account.api.get("/api/v1/analytics").json()

    created = session_account.api.post(
        "/api/v1/analytics/reports",
        json={"name": "Week 1 funnel", "description": "baseline", "report_type": "leads"},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["report_type"] == "leads"
    assert report["snapshot"]["leads_total"] == live["leads_total"]
    assert _buckets(report["snapshot"], "social_by_platform") == {"hackernews": 3}

    # New data changes the live summary; the saved report keeps what it captured.
    async def run() -> None:
        async with session_scope() as db:
            db.add(
                _business(
                    uuid.UUID(session_account.user_id), name="New Lead", website_status="unknown"
                )
            )

    asyncio.run(run())
    assert session_account.api.get("/api/v1/analytics").json()["leads_total"] == 4
    assert (
        session_account.api.get(f"/api/v1/analytics/reports/{report['id']}").json()["snapshot"][
            "leads_total"
        ]
        == 3
    )

    exported = session_account.api.get(f"/api/v1/analytics/reports/{report['id']}/export")
    assert exported.status_code == 200
    assert "leads_total,,3" in exported.text


def test_report_defaults_unknown_type_and_rejects_an_empty_name(session_account: Session) -> None:
    fallback = session_account.api.post(
        "/api/v1/analytics/reports",
        json={"name": "Anything", "report_type": "not-a-report"},
        headers=session_account.csrf_headers(),
    )
    assert fallback.status_code == 201
    assert fallback.json()["report_type"] == "analytics"

    blank = session_account.api.post(
        "/api/v1/analytics/reports",
        json={"name": ""},
        headers=session_account.csrf_headers(),
    )
    assert blank.status_code == 422


def test_reports_require_csrf_for_state_changes(session_account: Session) -> None:
    missing = session_account.api.post("/api/v1/analytics/reports", json={"name": "No token"})
    assert missing.status_code in (401, 403)


def test_reports_are_listed_paginated_and_owner_scoped(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    _seed(session_account.user_id)
    report_ids = set()
    for name in ("First", "Second"):
        created = session_account.api.post(
            "/api/v1/analytics/reports",
            json={"name": name, "report_type": "social"},
            headers=session_account.csrf_headers(),
        )
        assert created.status_code == 201
        report_ids.add(created.json()["id"])

    listed = session_account.api.get("/api/v1/analytics/reports").json()
    assert listed["total"] == 2
    assert {row["id"] for row in listed["items"]} == report_ids
    assert session_account.api.get(
        "/api/v1/analytics/reports", params={"limit": 1}
    ).json()["total"] == 2

    other = make_account()
    assert other.api.get("/api/v1/analytics/reports").json()["total"] == 0
    a_report = next(iter(report_ids))
    assert other.api.get(f"/api/v1/analytics/reports/{a_report}").status_code == 404
    assert other.api.get(f"/api/v1/analytics/reports/{a_report}/export").status_code == 404
    assert (
        other.api.delete(
            f"/api/v1/analytics/reports/{a_report}", headers=other.csrf_headers()
        ).status_code
        == 404
    )

    deleted = session_account.api.delete(
        f"/api/v1/analytics/reports/{a_report}", headers=session_account.csrf_headers()
    )
    assert deleted.status_code == 204
    assert session_account.api.get("/api/v1/analytics/reports").json()["total"] == 1
    assert session_account.api.get(f"/api/v1/analytics/reports/{a_report}").status_code == 404


def test_analytics_is_owner_scoped(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    _seed(session_account.user_id)
    other = make_account()
    body = other.api.get("/api/v1/analytics").json()
    assert body["leads_total"] == 0
    assert all(body[key] == [] for key in _BUCKET_KEYS)
