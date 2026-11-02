"""The Phase 2 gate: two real users, and proof that one cannot touch the other's data.

Ownership cannot be retrofitted by the frontend, so every assertion here goes
through the HTTP API using the second user's own session cookie. A cross-owner
request must return 404 rather than 403 — confirming that an id exists is itself
a leak.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.discovery.adapters.base import DiscoveredItem
from app.modules.discovery.pipeline import NormalizedBusiness, normalize_item
from app.modules.discovery.store_sql import SqlBusinessStore
from app.modules.sources.models import Source
from tests.conftest import Session, signed_in_client

RETRIEVED = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
SOURCE_SLUG = "searxng"


async def _seed_one(owner_id: uuid.UUID, name: str, domain: str) -> str:
    """Write one business through the real store, as this owner.

    Going through `SqlBusinessStore` rather than raw SQL is the point: it is the
    path production uses, so it is the path that can leak across owners.
    """
    async with session_scope() as db:
        if await db.scalar(select(Source.id).where(Source.slug == SOURCE_SLUG)) is None:
            db.add(
                Source(
                    name="SearXNG (self-hosted)",
                    slug=SOURCE_SLUG,
                    category="search",
                    adapter_key="searxng",
                    health_status="unknown",
                )
            )
            await db.flush()

        item = DiscoveredItem(
            external_id=None,
            source_url=f"https://{domain}/",
            title_hint=name,
            raw_data={
                "name": name,
                "website": f"https://{domain}",
                "city": "Bengaluru",
                "email": f"hello@{domain}",
                "phone": "098765 43210",
            },
        )
        business = normalize_item(
            item, source_slug=SOURCE_SLUG, retrieved_at=RETRIEVED, default_region="IN"
        )

        store = SqlBusinessStore(db, owner_user_id=owner_id)
        await store.upsert(business)
        assert store.skipped_provenance == 0, "an unregistered source would drop provenance"

        row = await db.scalar(
            select(Business.id).where(
                Business.owner_user_id == owner_id, Business.normalized_domain == domain
            )
        )
        assert row is not None, "seeded business did not persist"
        return str(row)


def seed(session: Session, name: str, domain: str) -> str:
    return asyncio.run(_seed_one(uuid.UUID(session.user_id), name, domain))


@pytest.fixture()
def two_users(make_account: Callable[[], Session]) -> dict[str, str | Session]:
    a = make_account()
    b = make_account()
    business_id = seed(a, "Spark Coffee Roasters", "sparkcoffee-a.in")
    return {"a": a, "b": b, "business_id": business_id}


def test_owner_sees_their_own_records(two_users: dict) -> None:
    a: Session = two_users["a"]
    listing = a.api.get("/api/v1/businesses")
    assert listing.status_code == 200
    body = listing.json()
    assert [item["name"] for item in body["items"]] == ["Spark Coffee Roasters"]
    assert body["total"] == 1


def test_other_owner_sees_nothing(two_users: dict) -> None:
    b: Session = two_users["b"]
    body = b.api.get("/api/v1/businesses").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_other_owner_cannot_read_the_record(two_users: dict) -> None:
    b: Session = two_users["b"]
    response = b.api.get(f"/api/v1/businesses/{two_users['business_id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_other_owner_cannot_shortlist_the_record(two_users: dict) -> None:
    a: Session = two_users["a"]
    b: Session = two_users["b"]
    business_id = two_users["business_id"]

    assert (
        b.api.post(
            f"/api/v1/businesses/{business_id}/shortlist", headers=b.csrf_headers()
        ).status_code
        == 404
    )

    # The owner's record is untouched: no stage row was created for them either.
    assert a.api.get(f"/api/v1/businesses/{business_id}/stage").json()["crm_stage"] is None


def test_owner_can_shortlist_their_own_record(two_users: dict) -> None:
    a: Session = two_users["a"]
    moved = a.api.post(
        f"/api/v1/businesses/{two_users['business_id']}/shortlist", headers=a.csrf_headers()
    )
    assert moved.status_code == 200
    assert moved.json()["crm_stage"] == "Shortlisted"


def test_other_owner_cannot_change_the_stage(two_users: dict) -> None:
    a: Session = two_users["a"]
    b: Session = two_users["b"]
    business_id = two_users["business_id"]

    assert (
        b.api.post(
            f"/api/v1/businesses/{business_id}/stage/Won", headers=b.csrf_headers()
        ).status_code
        == 404
    )
    assert a.api.get(f"/api/v1/businesses/{business_id}/stage").json()["crm_stage"] is None


def test_other_owner_cannot_delete_the_record(two_users: dict) -> None:
    a: Session = two_users["a"]
    b: Session = two_users["b"]
    business_id = two_users["business_id"]

    assert (
        b.api.delete(f"/api/v1/businesses/{business_id}", headers=b.csrf_headers()).status_code
        == 404
    )
    assert a.api.get(f"/api/v1/businesses/{business_id}").status_code == 200


def test_export_contains_only_the_callers_rows(two_users: dict) -> None:
    """The leak that turns a bug into an incident: a bulk export that ignores
    ownership hands over the whole database in one download."""
    a: Session = two_users["a"]
    b: Session = two_users["b"]

    assert "Spark Coffee Roasters" in a.api.get("/api/v1/businesses/export").text

    other_export = b.api.get("/api/v1/businesses/export").text
    assert "Spark Coffee Roasters" not in other_export
    # The header survives, so an empty result reads as empty rather than broken.
    assert other_export.splitlines()[0].startswith("name,primary_category")


def test_export_carries_provenance_and_verification_state(two_users: dict) -> None:
    """An export with no source column is a lead list nobody can re-verify or
    opt someone out of. `website_status` must still say unknown: nothing fetched it."""
    a: Session = two_users["a"]
    row = a.api.get(f"/api/v1/businesses/{two_users['business_id']}").json()
    assert row["source_slugs"] == [SOURCE_SLUG]
    assert row["source_urls"] == ["https://sparkcoffee-a.in/"]
    assert row["website_status"] == "unknown"

    csv_text = a.api.get("/api/v1/businesses/export").text
    assert SOURCE_SLUG in csv_text
    assert "unverified" in csv_text, "an extracted contact is not a verified contact"


def test_anonymous_caller_cannot_reach_any_endpoint(two_users: dict) -> None:
    business_id = two_users["business_id"]
    anonymous = signed_in_client()
    for method, path in (
        ("get", "/api/v1/businesses"),
        ("get", f"/api/v1/businesses/{business_id}"),
        ("get", "/api/v1/businesses/export"),
        ("post", f"/api/v1/businesses/{business_id}/shortlist"),
        ("delete", f"/api/v1/businesses/{business_id}"),
    ):
        response = getattr(anonymous, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} was not protected"


def test_each_owner_gets_their_own_pipeline_and_stages(two_users: dict) -> None:
    """A shared default pipeline would put two users' boards in one column and
    make every CRM statistic wrong for both of them."""
    from app.modules.crm.models import CrmPipeline

    async def count() -> tuple[int, int]:
        async with session_scope() as db:
            rows = await db.scalars(select(CrmPipeline))
            pipelines = list(rows)
            owners = {pipeline.owner_user_id for pipeline in pipelines}
            return len(pipelines), len(owners)

    a: Session = two_users["a"]
    a.api.post(f"/api/v1/businesses/{two_users['business_id']}/shortlist", headers=a.csrf_headers())

    total, distinct_owners = asyncio.run(count())
    assert total == distinct_owners, "pipelines must not be shared between owners"


def test_store_never_writes_for_another_owner(two_users: dict) -> None:
    """Direct proof at the persistence layer, independent of the HTTP routes:
    a store built for owner B cannot see or touch owner A's rows."""
    a_id = uuid.UUID(two_users["a"].user_id)
    b_id = uuid.UUID(two_users["b"].user_id)

    async def read_as_b() -> list[str]:
        async with session_scope() as db:
            store = SqlBusinessStore(db, owner_user_id=b_id)
            rows = await store.all()
            return [row.normalized_domain or "" for row in rows]

    assert asyncio.run(read_as_b()) == []

    async def read_as_a() -> list[str]:
        async with session_scope() as db:
            store = SqlBusinessStore(db, owner_user_id=a_id)
            return [row.normalized_domain or "" for row in await store.all()]

    assert "sparkcoffee-a.in" in asyncio.run(read_as_a())


def test_second_owner_can_store_a_same_named_business(two_users: dict) -> None:
    """Two unrelated businesses can share a name. Deduplication is scoped to the
    owner, so 'Spark Coffee' in two accounts must not merge into one record."""
    b: Session = two_users["b"]
    business_id = seed(b, "Spark Coffee Roasters", "sparkcoffee-b.in")

    assert b.api.get(f"/api/v1/businesses/{business_id}").status_code == 200
    assert two_users["a"].api.get(f"/api/v1/businesses/{business_id}").status_code == 404


def test_normalized_business_import_is_exercised() -> None:
    """Kept honest: the store consumes NormalizedBusiness objects produced by the
    pipeline, so a drift in that shape fails here rather than at runtime."""
    item = DiscoveredItem(
        external_id="x",
        source_url="https://cafe.in",
        website_hint="https://cafe.in",
        title_hint="Cafe",
        raw_data={},
    )
    business: NormalizedBusiness = normalize_item(
        item, source_slug="searxng", retrieved_at=RETRIEVED, default_region="IN"
    )
    assert business.normalized_domain == "cafe.in"
    assert business.website_status == "unknown"
