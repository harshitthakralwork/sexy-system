"""Phase 3: startup intelligence — records, evidence-labelled revenue, competitors, watchlists.

Every test drives the HTTP API against real persistence. Startups are created
through the same store path production uses, and assertions read the response or
the database back so a green test means the row actually exists. Ownership is the
core invariant: another user's startup must be invisible and immutable.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.conftest import Session


def _create_startup(
    account: Session,
    *,
    name: str = "Zerodha",
    website_url: str | None = "https://zerodha.com",
    status: str = "active",
    **extra,
) -> dict:
    payload = {"name": name, "website_url": website_url, "status": status, **extra}
    response = account.api.post("/api/v1/startups", json=payload, headers=account.csrf_headers())
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_startup_round_trip(session_account: Session) -> None:
    created = _create_startup(
        session_account,
        name="Razorpay",
        website_url="https://razorpay.com",
        industry="fintech",
        country="IN",
        funding_stage="Series F",
        source_slug="crunchbase",
        source_url="https://crunchbase.com/organization/razorpay",
    )
    assert created["name"] == "Razorpay"
    assert created["normalized_domain"] == "razorpay.com"
    assert created["industry"] == "fintech"
    assert created["source_slug"] == "crunchbase"

    listed = session_account.api.get("/api/v1/startups")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]

    detail = session_account.api.get(f"/api/v1/startups/{created['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["name"] == "Razorpay"
    assert detail_body["founders"] == []
    assert detail_body["revenue"] == []
    assert detail_body["competitors"] == []
    assert detail_body["watchlists"] == []


def test_domain_is_normalized_and_duplicates_conflict(session_account: Session) -> None:
    first = _create_startup(
        session_account, name="Cred", website_url="https://www.CRED.club/"
    )
    assert first["normalized_domain"] == "cred.club"

    duplicate = session_account.api.post(
        "/api/v1/startups",
        json={"name": "Cred Clone", "website_url": "https://cred.club"},
        headers=session_account.csrf_headers(),
    )
    assert duplicate.status_code == 409, duplicate.text


def test_another_user_cannot_read_or_delete(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()

    created = _create_startup(owner, name="Groww")

    assert other.api.get(f"/api/v1/startups/{created['id']}").status_code == 404
    assert (
        other.api.delete(
            f"/api/v1/startups/{created['id']}", headers=other.csrf_headers()
        ).status_code
        == 404
    )
    # The owner can still see it: the other user's attempts changed nothing.
    assert owner.api.get(f"/api/v1/startups/{created['id']}").status_code == 200


def test_revenue_evidence_classes_are_enforced(session_account: Session) -> None:
    startup = _create_startup(session_account, name="Zoho")

    # A "not_available" record must not carry an amount.
    not_available = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/revenue",
        json={"classification": "not_available", "amount": 1000000},
        headers=session_account.csrf_headers(),
    )
    assert not_available.status_code == 422, not_available.text

    # An unknown classification is rejected outright.
    unknown = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/revenue",
        json={"classification": "self_reported"},
        headers=session_account.csrf_headers(),
    )
    assert unknown.status_code == 422, unknown.text

    # An estimate must state its methodology.
    estimate = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/revenue",
        json={"classification": "estimated", "amount": 500000000, "currency": "INR"},
        headers=session_account.csrf_headers(),
    )
    assert estimate.status_code == 422, estimate.text

    # A verified record with evidence is accepted and stored with its label.
    verified = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/revenue",
        json={
            "classification": "verified",
            "amount": 1200000000,
            "currency": "INR",
            "revenue_period": "FY2025",
            "confidence": 90,
            "source_url": "https://example.com/audited",
        },
        headers=session_account.csrf_headers(),
    )
    assert verified.status_code == 201, verified.text
    assert verified.json()["classification"] == "verified"
    assert verified.json()["amount"] == 1200000000

    detail = session_account.api.get(f"/api/v1/startups/{startup['id']}")
    assert [record["classification"] for record in detail.json()["revenue"]] == ["verified"]


def test_competitor_self_reference_and_duplicate_prevented(session_account: Session) -> None:
    startup = _create_startup(session_account, name="PhonePe", website_url="https://phonepe.com")
    rival = _create_startup(session_account, name="Paytm", website_url="https://paytm.com")

    self_edge = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/competitors",
        json={"competitor_startup_id": startup["id"]},
        headers=session_account.csrf_headers(),
    )
    assert self_edge.status_code == 422, self_edge.text

    edge = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/competitors",
        json={"competitor_startup_id": rival["id"], "relationship_type": "direct"},
        headers=session_account.csrf_headers(),
    )
    assert edge.status_code == 201, edge.text
    assert edge.json()["competitor_startup_id"] == rival["id"]

    duplicate = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/competitors",
        json={"competitor_startup_id": rival["id"]},
        headers=session_account.csrf_headers(),
    )
    assert duplicate.status_code == 409, duplicate.text


def test_watchlist_round_trip_and_uniqueness(session_account: Session) -> None:
    startup = _create_startup(session_account, name="Swiggy")

    created = session_account.api.post(
        "/api/v1/startups/watchlists",
        json={"name": "Food delivery", "description": "Track the incumbents"},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    watchlist_id = created.json()["id"]

    added = session_account.api.post(
        f"/api/v1/startups/watchlists/{watchlist_id}/items",
        json={"startup_id": startup["id"]},
        headers=session_account.csrf_headers(),
    )
    assert added.status_code == 201, added.text

    again = session_account.api.post(
        f"/api/v1/startups/watchlists/{watchlist_id}/items",
        json={"startup_id": startup["id"]},
        headers=session_account.csrf_headers(),
    )
    assert again.status_code == 409, again.text

    watchlists = session_account.api.get("/api/v1/startups/watchlists")
    assert watchlists.status_code == 200
    body = watchlists.json()
    assert len(body) == 1
    assert [item["id"] for item in body[0]["items"]] == [startup["id"]]

    removed = session_account.api.delete(
        f"/api/v1/startups/watchlists/{watchlist_id}/items/{startup['id']}",
        headers=session_account.csrf_headers(),
    )
    assert removed.status_code == 200

    after = session_account.api.get("/api/v1/startups/watchlists")
    assert after.json()[0]["items"] == []


def test_research_updates_last_researched_at(session_account: Session) -> None:
    startup = _create_startup(session_account, name="Ola Electric")
    assert startup["last_researched_at"] is None

    research = session_account.api.post(
        f"/api/v1/startups/{startup['id']}/research",
        json={
            "research_type": "competitive_scan",
            "summary": "Expanding into cell manufacturing.",
            "findings": {"market": "EV two-wheelers"},
            "source_references": {"crunchbase": "https://example.com/ola"},
        },
        headers=session_account.csrf_headers(),
    )
    assert research.status_code == 201, research.text

    detail = session_account.api.get(f"/api/v1/startups/{startup['id']}")
    body = detail.json()
    assert body["last_researched_at"] is not None
    assert len(body["research"]) == 1
    assert body["research"][0]["research_type"] == "competitive_scan"


def test_update_startup_rejects_unknown_status(session_account: Session) -> None:
    startup = _create_startup(session_account, name="Dunzo")

    bad = session_account.api.patch(
        f"/api/v1/startups/{startup['id']}",
        json={"status": "pivoting"},
        headers=session_account.csrf_headers(),
    )
    assert bad.status_code == 422, bad.text

    good = session_account.api.patch(
        f"/api/v1/startups/{startup['id']}",
        json={"status": "acquired", "funding_stage": "Acquired"},
        headers=session_account.csrf_headers(),
    )
    assert good.status_code == 200, good.text
    assert good.json()["status"] == "acquired"
