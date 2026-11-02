"""Map-Based Business Discovery, end to end against real PostgreSQL.

Everything here goes through the HTTP API and then reads the database back, because
the feature is only real if a drawn shape becomes a job, the job becomes stored
businesses, and those businesses come back as pins that belong to the user who
searched for them.

Stub adapters replace the network only. Geometry validation, the tile planner, the
deduplication, the store and ownership are the shipped code.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.discovery.adapters.base import AccessDeniedError
from app.modules.discovery.models import DiscoveryJob, JobBatch, SearchArea, SourceRecord
from app.modules.discovery.schemas import query_from_config
from app.shared.geo import area_to_payload
from tests.conftest import Session
from tests.discovery_doubles import (
    StubAdapter,
    item,
    unique_domain,
)

HISAR = {"latitude": 29.1499, "longitude": 75.7211}


def circle(radius_km: float, **extra: Any) -> dict[str, Any]:
    return {
        "shape_type": "circle",
        "latitude": HISAR["latitude"],
        "longitude": HISAR["longitude"],
        "radius_km": radius_km,
        **extra,
    }


def post_area(account: Session, payload: dict[str, Any]) -> Any:
    return account.api.post(
        "/api/v1/discovery/areas",
        json=payload,
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )


def read_job(job_id: uuid.UUID) -> dict[str, Any]:
    async def load() -> dict[str, Any]:
        async with session_scope() as session:
            job = await session.get(DiscoveryJob, job_id)
            assert job is not None
            return {
                "status": job.status,
                "total": job.total_records,
                "processed": job.processed_records,
                "progress": float(job.progress_percent),
                "report": job.report,
                "error_details": job.error_details,
            }

    return asyncio.run(load())


def batches_for(job_id: uuid.UUID) -> list[dict[str, Any]]:
    async def load() -> list[dict[str, Any]]:
        async with session_scope() as session:
            rows = (
                await session.scalars(
                    select(JobBatch)
                    .where(JobBatch.job_id == job_id)
                    .order_by(JobBatch.batch_number)
                )
            ).all()
            return [
                {
                    "unit_kind": row.unit_kind,
                    "tile_key": row.tile_key,
                    "status": row.status,
                    "truncated": row.truncated,
                    "bounds": row.bounds,
                    "retry_count": row.retry_count,
                }
                for row in rows
            ]

    return asyncio.run(load())


def business_count(owner_id: uuid.UUID) -> int:
    async def load() -> int:
        async with session_scope() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(Business)
                .where(Business.owner_user_id == owner_id)
            )
            return int(total or 0)

    return asyncio.run(load())


def record_count(owner_id: uuid.UUID) -> int:
    async def load() -> int:
        async with session_scope() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(SourceRecord)
                    .where(SourceRecord.owner_user_id == owner_id)
                )
                or 0
            )

    return asyncio.run(load())


# --------------------------------------------------------------- saved areas


def test_a_saved_circle_keeps_the_geometry_it_was_given(session_account: Session) -> None:
    response = post_area(
        session_account,
        {
            "name": "Hisar centre",
            "geometry": circle(3.0),
            "categories": ["amenity=hospital"],
        },
    )
    assert response.status_code == 201, response.text
    area = response.json()

    assert area["shape_type"] == "circle"
    assert area["radius_m"] == 3000
    # 28.3 km², computed here rather than trusted from the client.
    assert area["area_km2"] == pytest.approx(28.27, abs=0.2)
    assert area["bbox_west"] < area["bbox_east"]
    assert area["bbox_south"] < area["bbox_north"]
    assert area["categories"] == ["amenity=hospital"]


def test_a_polygon_is_stored_as_drawn(session_account: Session) -> None:
    ring = [
        [29.10, 75.70],
        [29.10, 75.78],
        [29.18, 75.78],
        [29.18, 75.70],
    ]
    response = post_area(
        session_account, {"name": "Square", "geometry": {"shape_type": "polygon", "polygon": ring}}
    )
    assert response.status_code == 201, response.text
    stored = response.json()
    assert stored["shape_type"] == "polygon"
    assert len(stored["polygon"]) == 4
    # Hand-computed reference, not the function's own answer: 0.08 deg of longitude
    # (0.08 x 111.32 x cos 29.14 = 7.78 km) by 0.08 deg of latitude (8.85 km).
    assert stored["area_km2"] == pytest.approx(68.8, abs=0.6)


@pytest.mark.parametrize(
    "geometry,problem",
    [
        ({"shape_type": "polygon", "polygon": [[29.1, 75.7], [29.2, 75.8]]}, "at least 3 vertices"),
        ({"shape_type": "circle", "latitude": 95.0, "longitude": 75.7, "radius_km": 2}, "latitude"),
        ({"shape_type": "circle", "latitude": 29.1, "longitude": 75.7, "radius_km": 400}, "radius"),
        ({"shape_type": "circle", "latitude": 29.1, "longitude": 75.7}, "needs"),
        ({"shape_type": "rectangle"}, "rectangle"),
        ({"shape_type": "administrative"}, "bounding box"),
    ],
)
def test_unusable_geometry_is_refused_not_stored(
    session_account: Session, geometry: dict[str, Any], problem: str
) -> None:
    response = post_area(session_account, {"name": "Bad", "geometry": geometry})
    assert response.status_code == 422, response.text
    assert problem.lower() in json.dumps(response.json()).lower()


def test_an_area_larger_than_the_ceiling_is_refused_with_the_number(
    session_account: Session,
) -> None:
    """Silently shrinking a drawn area would turn 'not searched' into 'nothing there'."""
    response = post_area(session_account, {"name": "Huge", "geometry": circle(50.0)})
    assert response.status_code == 422
    body = json.dumps(response.json())
    assert "km²" in body or "km" in body
    assert "limit_km2" in body


def test_another_user_cannot_read_update_or_delete_the_area(
    make_account: Callable[[], Session],
) -> None:
    owner = make_account()
    intruder = make_account()
    created = post_area(owner, {"name": "Mine", "geometry": circle(1.0)}).json()
    area_id = created["id"]
    headers = {**intruder.csrf_headers(), "Origin": "http://localhost:3000"}

    assert intruder.api.get(f"/api/v1/discovery/areas/{area_id}").status_code == 404
    replacement = {"name": "Yours now", "geometry": circle(1.0)}
    assert intruder.api.put(
        f"/api/v1/discovery/areas/{area_id}", json=replacement, headers=headers
    ).status_code == 404
    updated = intruder.api.put(
        f"/api/v1/discovery/areas/{area_id}", json=replacement, headers=headers
    )
    assert updated.status_code == 404
    deleted = intruder.api.delete(f"/api/v1/discovery/areas/{area_id}", headers=headers)
    assert deleted.status_code == 404
    # Still the owner's, unchanged.
    assert owner.api.get(f"/api/v1/discovery/areas/{area_id}").json()["name"] == "Mine"


def test_a_deleted_area_stops_being_selectable_but_keeps_history(
    session_account: Session,
) -> None:
    created = post_area(session_account, {"name": "Temp", "geometry": circle(1.0)}).json()
    headers = {**session_account.csrf_headers(), "Origin": "http://localhost:3000"}

    deleted = session_account.api.delete(
        f"/api/v1/discovery/areas/{created['id']}", headers=headers
    )
    assert deleted.status_code == 204
    assert created["id"] not in [
        row["id"] for row in session_account.api.get("/api/v1/discovery/areas").json()["items"]
    ]

    async def still_there() -> bool:
        async with session_scope() as session:
            row = await session.get(SearchArea, uuid.UUID(created["id"]))
            return row is not None and row.deleted_at is not None

    assert asyncio.run(still_there())


def test_writing_an_area_requires_the_csrf_token(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/discovery/areas",
        json={"name": "No CSRF", "geometry": circle(1.0)},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------- tiled jobs


def test_a_small_area_runs_as_one_unit_and_stores_what_it_found(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    domain = unique_domain()
    stub = StubAdapter(items=[item(domain, "Gantai Chira Hospital")])
    stub_adapters([stub])

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={
            "category": "amenity=hospital",
            "geometry": circle(2.0),
            "sources": ["overpass"],
        },
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text
    job_id = uuid.UUID(created.json()["id"])

    job = read_job(job_id)
    assert job["status"] == "completed"
    assert job["report"]["totals"]["stored_new"] == 1
    assert job["report"]["area"]["shape_type"] == "circle"
    assert len(batches_for(job_id)) == 1
    assert stub.queries[0].location is not None
    assert stub.queries[0].category == "amenity=hospital"

    names = [row["name"] for row in session_account.api.get("/api/v1/businesses").json()["items"]]
    assert "Gantai Chira Hospital" in names


def test_a_large_area_runs_as_deterministic_tiles_with_visible_state(
    session_account: Session,
    stub_adapters: Callable[[list[StubAdapter]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One tile per unit of ground, each with its own row — that is what makes a
    partly covered region reportable as partly covered."""
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Tile Shop")])])
    monkeypatch.setenv("SPARKX_DISCOVERY_TILE_TARGET_AREA_KM2", "1")
    monkeypatch.setenv("SPARKX_DISCOVERY_MAX_TILES_PER_JOB", "20")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"category": "shop", "geometry": circle(2.0), "sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text
    job_id = uuid.UUID(created.json()["id"])

    # A 2 km circle is a 4.0 x 4.0 km box: 4 columns x 4 rows at a 1 km² target.
    batches = batches_for(job_id)
    assert len(batches) == 16
    assert len({batch["tile_key"] for batch in batches}) == 16
    assert all(batch["unit_kind"] == "tile" for batch in batches)
    assert all(batch["status"] == "completed" for batch in batches)
    assert all(batch["bounds"] is not None for batch in batches)

    job = read_job(job_id)
    assert job["report"]["totals"]["units_total"] == 16
    # The stub hands back one record per tile, so the same business is sighted 16
    # times across the grid. Tiling must produce 16 sightings and one lead — 16
    # leads would mean the deduplication rules are being bypassed by tile shape.
    assert job["report"]["totals"]["stored_new"] == 1
    assert job["report"]["known_records_reseen"] == 15


def test_a_region_needing_more_tiles_than_allowed_is_refused_before_it_runs(
    session_account: Session,
    stub_adapters: Callable[[list[StubAdapter]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_adapters([StubAdapter(items=[])])
    monkeypatch.setenv("SPARKX_DISCOVERY_TILE_TARGET_AREA_KM2", "1")
    monkeypatch.setenv("SPARKX_DISCOVERY_MAX_TILES_PER_JOB", "4")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()

    response = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"category": "shop", "geometry": circle(20.0), "sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 422
    assert "tiles_required" in json.dumps(response.json())


def test_a_truncated_tile_is_subdivided_and_reported(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    """Exactly `limit` records means the provider stopped early, so the true count
    is unknown. The job must say which parts of the area are not fully covered."""
    shops = [item(unique_domain(), f"Shop {index}") for index in range(3)]
    stub = StubAdapter(items=shops, capped=True)
    stub_adapters([stub])

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={
            "category": "shop",
            "geometry": circle(1.0),
            "sources": ["overpass"],
            "max_results": 3,
        },
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    job_id = uuid.UUID(created.json()["id"])

    job = read_job(job_id)
    assert job["report"]["totals"]["units_truncated"] >= 1
    assert job["error_details"]["truncated_units"] >= 1
    assert "not completely covered" in job["error_details"]["note"]

    truncated_batches = [batch for batch in batches_for(job_id) if batch["truncated"]]
    assert truncated_batches


def test_a_source_that_refuses_leaves_the_job_honest_not_optimistic(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(error=AccessDeniedError("instance at capacity"))])

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"category": "amenity=hospital", "geometry": circle(1.0), "sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    job = read_job(uuid.UUID(created.json()["id"]))

    assert job["status"] == "failed"
    assert job["total"] == 0
    assert "access_denied" in str(job["error_details"])


def test_a_job_can_be_asked_for_a_saved_area_and_remembers_it(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Sector 4 Clinic")])])
    area = post_area(session_account, {"name": "Sector 4", "geometry": circle(1.5)}).json()

    created = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={"category": "amenity=clinic", "area_id": area["id"], "sources": ["overpass"]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["area_id"] == area["id"]

    async def area_was_run() -> bool:
        async with session_scope() as session:
            row = await session.get(SearchArea, uuid.UUID(area["id"]))
            return row is not None and row.last_run_at is not None

    assert asyncio.run(area_was_run())


def test_a_job_cannot_be_created_with_both_a_shape_and_a_saved_area(
    session_account: Session,
) -> None:
    """Ambiguous provenance: the record would not say what was actually searched."""
    area = post_area(session_account, {"name": "Ambiguous", "geometry": circle(1.0)}).json()
    response = session_account.api.post(
        "/api/v1/discovery/jobs",
        json={
            "category": "shop",
            "area_id": area["id"],
            "geometry": circle(2.0),
            "sources": ["overpass"],
        },
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------- cross-tile identity


def test_the_same_source_record_found_twice_stays_one_business(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    """Overlapping areas and re-runs are the same event: OSM says node/12345, so it
    is one business with two sightings, not two leads."""
    owner_id = uuid.UUID(session_account.user_id)
    domain = unique_domain()
    shared = item(domain, "Rose Cafe", external_id="node/12345")
    stub_adapters([StubAdapter(items=[shared])])

    payload = {"category": "amenity=cafe", "geometry": circle(1.0), "sources": ["overpass"]}
    headers = {**session_account.csrf_headers(), "Origin": "http://localhost:3000"}
    first = session_account.api.post("/api/v1/discovery/jobs", json=payload, headers=headers)
    # The first sighting has nothing to match against; it creates the record.
    assert read_job(uuid.UUID(first.json()["id"]))["report"]["known_records_reseen"] == 0

    second = session_account.api.post("/api/v1/discovery/jobs", json=payload, headers=headers)
    assert read_job(uuid.UUID(second.json()["id"]))["report"]["known_records_reseen"] >= 1

    assert business_count(owner_id) == 1
    # Two sightings, one business: provenance records every time it was seen.
    assert record_count(owner_id) == 2

    items = session_account.api.get("/api/v1/businesses").json()["items"]
    rose = [row for row in items if row["name"] == "Rose Cafe"]
    assert len(rose) == 1

    detail = session_account.api.get(f"/api/v1/businesses/{rose[0]['id']}").json()
    # One business, one named source, two sightings underneath it.
    assert set(detail["source_slugs"]) == {"overpass"}


# ------------------------------------------------------------------- viewport


def test_the_viewport_returns_only_records_inside_it(
    session_account: Session,
) -> None:
    owner_id = uuid.UUID(session_account.user_id)

    async def seed() -> None:
        async with session_scope() as session:
            for name, lat, lon in (("Near", 29.15, 75.72), ("Far", 12.97, 77.59)):
                session.add(
                    Business(
                        owner_user_id=owner_id,
                        name=name,
                        latitude=lat,
                        longitude=lon,
                        website_status="unknown",
                        first_discovered_at=_now(),
                    )
                )

    asyncio.run(seed())
    bbox = "75.62,29.05,75.82,29.25"
    response = session_account.api.get(f"/api/v1/businesses/viewport?bbox={bbox}")
    assert response.status_code == 200
    body = response.json()

    assert [pin["name"] for pin in body["items"]] == ["Near"]
    assert body["total_in_viewport"] == 1
    assert body["truncated"] is False


def test_the_viewport_says_when_it_left_records_out(
    session_account: Session,
) -> None:
    owner_id = uuid.UUID(session_account.user_id)

    async def seed() -> None:
        async with session_scope() as session:
            for index in range(5):
                session.add(
                    Business(
                        owner_user_id=owner_id,
                        name=f"Shop {index}",
                        latitude=29.15 + index * 0.001,
                        longitude=75.72,
                        website_status="unknown",
                        first_discovered_at=_now(),
                    )
                )

    asyncio.run(seed())
    response = session_account.api.get(
        "/api/v1/businesses/viewport?bbox=75.62,29.05,75.82,29.25&limit=2"
    )
    body = response.json()

    assert body["returned"] == 2
    assert body["total_in_viewport"] == 5
    assert body["truncated"] is True


def test_records_without_coordinates_are_counted_but_never_pinned(
    session_account: Session,
) -> None:
    """A source that named a business but not its position is a real result the map
    cannot draw. Dropping it from the totals would understate the market."""
    owner_id = uuid.UUID(session_account.user_id)

    async def seed() -> None:
        async with session_scope() as session:
            session.add(
                Business(
                    owner_user_id=owner_id,
                    name="Unmapped Tailor",
                    latitude=None,
                    longitude=None,
                    website_status="unknown",
                    first_discovered_at=_now(),
                )
            )

    asyncio.run(seed())
    listed = session_account.api.get("/api/v1/businesses").json()
    assert any(row["name"] == "Unmapped Tailor" for row in listed["items"])

    viewport = session_account.api.get(
        "/api/v1/businesses/viewport?bbox=75.0,29.0,76.0,29.5"
    ).json()
    assert viewport["items"] == []


def test_an_unusable_viewport_bbox_is_refused(session_account: Session) -> None:
    for bad in ("", "75.0,29.0", "not,a,bbox", "76.0,29.0,75.0,29.5"):
        response = session_account.api.get(f"/api/v1/businesses/viewport?bbox={bad}")
        assert response.status_code == 422, bad


def test_one_user_cannot_see_another_user_s_pins(
    make_account: Callable[[], Session], stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    owner = make_account()
    intruder = make_account()
    stub_adapters([StubAdapter(items=[item(unique_domain(), "Owner Only Shop")])])

    session_api: TestClient = owner.api
    created = session_api.post(
        "/api/v1/discovery/jobs",
        json={"category": "shop", "geometry": circle(1.0), "sources": ["overpass"]},
        headers={**owner.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert created.status_code == 201
    read_job(uuid.UUID(created.json()["id"]))

    pins = intruder.api.get("/api/v1/businesses/viewport?bbox=75.62,29.05,75.82,29.25").json()
    assert pins["items"] == []
    assert pins["total_in_viewport"] == 0


# --------------------------------------------------------------------- export


def test_selected_export_returns_the_picked_records_only(
    session_account: Session,
) -> None:
    owner_id = uuid.UUID(session_account.user_id)

    async def seed() -> None:
        async with session_scope() as session:
            for name in ("Keep", "Also Keep", "Not Selected"):
                session.add(
                    Business(
                        owner_user_id=owner_id,
                        name=name,
                        website_status="unknown",
                        first_discovered_at=_now(),
                    )
                )
            return [(await session.scalars(select(Business).where(Business.name == name))).one().id
                    for name in ("Keep", "Also Keep")]

    ids = asyncio.run(seed())
    response = session_account.api.post(
        "/api/v1/businesses/export/selected",
        json={"ids": [str(bid) for bid in ids]},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200, response.text
    body = response.text

    assert "Keep" in body and "Also Keep" in body and "Not Selected" not in body
    assert response.headers["X-Exported-Records"] == "2"
    assert response.headers["X-Export-Skipped"] == "0"
    assert "source_slugs" in body.splitlines()[0]


def test_exporting_another_user_s_records_reports_them_as_skipped(
    make_account: Callable[[], Session],
) -> None:
    """The ids are someone else's, so nothing is exported — and the response says
    so instead of quietly returning a shorter file."""
    owner = make_account()
    intruder = make_account()

    async def seed() -> uuid.UUID:
        async with session_scope() as session:
            business = Business(
                owner_user_id=uuid.UUID(owner.user_id),
                name="Private Lead",
                website_status="unknown",
                first_discovered_at=_now(),
            )
            session.add(business)
            await session.flush()
            return business.id

    private_id = asyncio.run(seed())
    response = intruder.api.post(
        "/api/v1/businesses/export/selected",
        json={"ids": [str(private_id)]},
        headers={**intruder.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers["X-Exported-Records"] == "0"
    assert response.headers["X-Export-Skipped"] == "1"
    assert "Private Lead" not in response.text


def test_selected_export_requires_the_csrf_token(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/businesses/export/selected",
        json={"ids": [str(uuid.uuid4())]},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 403


def test_an_empty_selection_is_refused(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/businesses/export/selected",
        json={"ids": []},
        headers={**session_account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ rate limits


def test_queuing_too_many_jobs_is_throttled(
    session_account: Session, stub_adapters: Callable[[list[StubAdapter]], None]
) -> None:
    """Every accepted job means provider requests. A runaway page must not be able
    to queue hundreds of sweeps in a minute."""
    stub_adapters([StubAdapter(items=[])])
    headers = {**session_account.csrf_headers(), "Origin": "http://localhost:3000"}
    statuses = []
    for _ in range(12):
        response = session_account.api.post(
            "/api/v1/discovery/jobs",
            json={"category": "shop", "geometry": circle(0.5), "sources": ["overpass"]},
            headers=headers,
        )
        statuses.append(response.status_code)
        if response.status_code == 429:
            assert "Retry-After" in response.headers
            break

    assert 429 in statuses


def test_a_saved_area_can_be_re_read_and_its_geometry_round_trips(
    session_account: Session,
) -> None:
    ring = [[29.10, 75.70], [29.10, 75.80], [29.20, 75.80]]
    created = post_area(
        session_account,
        {"name": "Triangle", "geometry": {"shape_type": "polygon", "polygon": ring}},
    ).json()

    async def round_trip() -> tuple[Any, Any]:
        async with session_scope() as session:
            row = await session.get(SearchArea, uuid.UUID(created["id"]))
            assert row is not None
            from app.modules.discovery.areas import area_from_row

            payload = area_to_payload(area_from_row(row))
            request, area = query_from_config(
                {"keywords": ["x"], "category": "shop", "resolved_area": payload}
            )
            assert request.category == "shop"
            return row, area

    row, area = asyncio.run(round_trip())
    assert area is not None
    assert area.bbox.as_tuple() == (
        pytest.approx(float(row.bbox_west)),
        pytest.approx(float(row.bbox_south)),
        pytest.approx(float(row.bbox_east)),
        pytest.approx(float(row.bbox_north)),
    )


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)
