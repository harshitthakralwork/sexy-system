"""Phase 2: leads intelligence — qualification, CRM board and business notes/tags.

Every test drives the HTTP API against real persistence. Businesses are inserted
through the same store path production uses (or directly, for signal-precise
qualification cases), and assertions read the database back so a green test means
the row actually exists, not just that a response echoed what was sent.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.services_catalog.models import BusinessOpportunity, OpportunityEvidence
from tests.conftest import Session


def _insert_business(
    owner_id: str,
    *,
    name: str = "Spark Cafe",
    domain: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    category: str | None = None,
    website_status: str = "unknown",
    signals: dict | None = None,
) -> str:
    async def run() -> str:
        async with session_scope() as db:
            business = Business(
                owner_user_id=uuid.UUID(owner_id),
                name=name,
                normalized_name=name.lower(),
                normalized_domain=domain,
                normalized_phone=phone,
                normalized_email=email,
                primary_category=category,
                website_url=f"https://{domain}" if domain else None,
                website_status=website_status,
                phone=phone,
                email=email,
                enrichment={"signals": signals or {}},
                first_discovered_at=datetime.now(UTC),
            )
            db.add(business)
            await db.flush()
            return str(business.id)

    return asyncio.run(run())


def _default_service_id(account: Session) -> str:
    listed = account.api.get("/api/v1/services")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert items, "default catalog did not seed"
    return items[0]["id"]


def test_default_catalog_is_seeded_with_rules(session_account: Session) -> None:
    listed = session_account.api.get("/api/v1/services")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "web-presence"

    detail = session_account.api.get(f"/api/v1/services/{items[0]['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["profiles"]) == 1
    rules = body["profiles"][0]["rules"]
    assert len(rules) == 5
    assert {rule["signal_key"] for rule in rules} >= {
        "website_claimed",
        "website_status",
        "phone_present",
        "email_present",
        "category_matched",
    }


def test_qualification_scores_the_observed_signals(session_account: Session) -> None:
    service_id = _default_service_id(session_account)
    business_id = _insert_business(
        session_account.user_id,
        phone="09876543210",
        email="hello@sparkcafe.in",
        category="cafe",
        signals={"website_claimed": False},
    )

    response = session_account.api.post(
        f"/api/v1/services/{service_id}/qualify/{business_id}",
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # 40 (no website) + 15 (phone) + 15 (email) + 10 (category) = 80 of 100.
    assert body["score"] == 80.0
    assert body["status"] == "qualified"
    assert body["confidence"] == 100.0
    contributions = {row["evidence_type"]: row["score_contribution"] for row in body["evidence"]}
    assert contributions["website_claimed"] == 40.0
    assert contributions["phone_present"] == 15.0
    descriptions = [row["description"] for row in body["evidence"]]
    assert any(description.startswith("No website stated") for description in descriptions)


def test_qualification_reports_missing_signals_instead_of_inventing_them(
    session_account: Session,
) -> None:
    service_id = _default_service_id(session_account)
    business_id = _insert_business(
        session_account.user_id,
        domain="sparkcafe.in",
        website_status="available",
    )

    response = session_account.api.post(
        f"/api/v1/services/{service_id}/qualify/{business_id}",
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # A business with a working website and no contact data scores nothing.
    assert body["score"] == 0.0
    assert body["status"] == "unqualified"
    # Phone, email and category were never observed, so confidence must drop.
    assert body["confidence"] < 100.0
    assert "phone_present" in body["missing_information"]
    assert "email_present" in body["missing_information"]
    assert "category_matched" in body["missing_information"]


def test_requalification_replaces_the_previous_result(session_account: Session) -> None:
    service_id = _default_service_id(session_account)
    business_id = _insert_business(
        session_account.user_id,
        phone="09876543210",
        email="hello@sparkcafe.in",
        category="cafe",
        signals={"website_claimed": False},
    )
    headers = session_account.csrf_headers()

    first = session_account.api.post(
        f"/api/v1/services/{service_id}/qualify/{business_id}", headers=headers
    )
    second = session_account.api.post(
        f"/api/v1/services/{service_id}/qualify/{business_id}", headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["score"] == second.json()["score"]

    async def read_db() -> tuple[int, int]:
        async with session_scope() as db:
            opportunity = await db.scalar(
                select(BusinessOpportunity).where(
                    BusinessOpportunity.business_id == uuid.UUID(business_id)
                )
            )
            assert opportunity is not None
            evidence_count = await db.scalar(
                select(func.count())
                .select_from(OpportunityEvidence)
                .where(OpportunityEvidence.opportunity_id == opportunity.id)
            )
            return 1, int(evidence_count or 0)

    opportunities, evidence = asyncio.run(read_db())
    assert opportunities == 1, "requalification must update, not stack, the opportunity"
    assert evidence == 5, "evidence rows are replaced, not appended"


def test_another_user_cannot_qualify_or_read_the_service(
    make_account: Callable[[], Session],
) -> None:
    owner: Session = make_account()
    other: Session = make_account()

    service_id = _default_service_id(owner)
    business_id = _insert_business(owner.user_id, phone="09876543210")

    assert (
        other.api.post(
            f"/api/v1/services/{service_id}/qualify/{business_id}",
            headers=other.csrf_headers(),
        ).status_code
        == 404
    )
    assert other.api.get(f"/api/v1/services/{service_id}").status_code == 404


def test_crm_board_seeds_default_stages_and_shows_cards(session_account: Session) -> None:
    business_id = _insert_business(session_account.user_id, name="Filter Coffee House")

    pipelines = session_account.api.get("/api/v1/crm/pipelines")
    assert pipelines.status_code == 200
    stages = pipelines.json()[0]["stages"]
    assert [stage["name"] for stage in stages] == [
        "New",
        "Researched",
        "Qualified",
        "Shortlisted",
        "Contacted",
        "Follow-up",
        "Interested",
        "Meeting Scheduled",
        "Proposal Sent",
        "Won",
        "Lost",
        "Archived",
    ]

    shortlisted = session_account.api.post(
        f"/api/v1/businesses/{business_id}/shortlist", headers=session_account.csrf_headers()
    )
    assert shortlisted.status_code == 200

    board = session_account.api.get("/api/v1/crm/board")
    assert board.status_code == 200
    body = board.json()
    assert len(body["stages"]) == 12
    card = next(card for card in body["cards"] if card["business_id"] == business_id)
    assert card["stage_name"] == "Shortlisted"
    assert card["name"] == "Filter Coffee House"


def test_custom_stage_creation_and_rename(session_account: Session) -> None:
    created = session_account.api.post(
        "/api/v1/crm/stages",
        json={"name": "In negotiation"},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    stage_id = created.json()["id"]

    renamed = session_account.api.patch(
        f"/api/v1/crm/stages/{stage_id}",
        json={"name": "Negotiating"},
        headers=session_account.csrf_headers(),
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Negotiating"

    duplicate = session_account.api.post(
        "/api/v1/crm/stages",
        json={"name": "Negotiating"},
        headers=session_account.csrf_headers(),
    )
    assert duplicate.status_code == 422


def test_stage_change_writes_an_activity(session_account: Session) -> None:
    business_id = _insert_business(session_account.user_id, name="Prospect Ltd")

    moved = session_account.api.post(
        f"/api/v1/businesses/{business_id}/stage/Researched",
        headers=session_account.csrf_headers(),
    )
    assert moved.status_code == 200, moved.text

    activities = session_account.api.get(f"/api/v1/crm/activities?business_id={business_id}")
    assert activities.status_code == 200
    body = activities.json()
    assert body["total"] == 1
    assert body["items"][0]["activity_type"] == "stage_change"
    assert body["items"][0]["title"] == "Moved to Researched"


def test_notes_and_tags_round_trip(session_account: Session) -> None:
    business_id = _insert_business(session_account.user_id, name="Noted Business")
    headers = session_account.csrf_headers()

    created = session_account.api.post(
        f"/api/v1/businesses/{business_id}/notes",
        json={"content": "Spoke to the owner; wants a site by Diwali."},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    notes = session_account.api.get(f"/api/v1/businesses/{business_id}/notes")
    assert notes.status_code == 200
    assert [note["content"] for note in notes.json()] == [
        "Spoke to the owner; wants a site by Diwali."
    ]

    assigned = session_account.api.put(
        f"/api/v1/businesses/{business_id}/tags",
        json={"names": ["priority", "local"]},
        headers=headers,
    )
    assert assigned.status_code == 200
    assert sorted(tag["name"] for tag in assigned.json()) == ["local", "priority"]

    on_business = session_account.api.get(f"/api/v1/businesses/{business_id}/tags")
    assert sorted(tag["name"] for tag in on_business.json()) == ["local", "priority"]

    all_tags = session_account.api.get("/api/v1/businesses/tags")
    assert all_tags.status_code == 200
    assert {tag["name"] for tag in all_tags.json()} >= {"local", "priority"}


def test_unknown_business_is_404_for_notes_and_qualification(session_account: Session) -> None:
    service_id = _default_service_id(session_account)
    missing = str(uuid.uuid4())

    assert (
        session_account.api.get(f"/api/v1/businesses/{missing}/notes").status_code == 404
    )
    assert (
        session_account.api.post(
            f"/api/v1/services/{service_id}/qualify/{missing}",
            headers=session_account.csrf_headers(),
        ).status_code
        == 404
    )
