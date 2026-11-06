from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.businesses.models import Business
from app.modules.discovery.deduplication import (
    matches_existing_business,
    merge_candidate_into_business,
)
from app.modules.discovery.provenance import (
    EXTRACTION_CONFIDENCE,
    FieldEvidence,
    classify_source_type,
    determine_website_status,
    is_directory_url,
    is_official_website,
    sanitize_address,
    should_update_field,
)
from app.modules.discovery.public_fetch import PublicPageFetchResult
from app.modules.discovery.scan_adapters import RawCandidate, _extract_public_phone
from app.modules.discovery.scan_planner import build_scan_plan
from app.modules.discovery.scan_service import (
    build_field_status,
    compute_completeness_status,
)
from tests.conftest import Session

pytestmark = pytest.mark.no_source_observability

# ── 1. Unit Tests (Pure, No Live Network, No Database Required) ───────────────


def test_source_classification() -> None:
    jd_url = "https://www.justdial.com/Delhi/Dentists/nct-10156410"
    assert classify_source_type(jd_url) == "justdial"
    assert (
        classify_source_type("https://www.google.com/maps/place/Apollo+Dental/@28.5,77.2")
        == "google_maps"
    )
    assert classify_source_type("https://www.yelp.com/biz/dental-care-delhi") == "directory"
    assert classify_source_type("https://www.yellowpages.com/nyc/plumbers") == "directory"
    assert classify_source_type("https://apollodentaldelhi.com") == "website"
    assert classify_source_type("https://drsharmaclinic.in/contact") == "website"


def test_maps_phone_extraction_rejects_internal_ids() -> None:
    strings = [
        "4306215837336208023",
        "113452138473556115552",
        "077748 88116",
        "+91 77748 88116",
        "tel:07774888116",
    ]
    assert _extract_public_phone(strings) == "07774888116"
    assert _extract_public_phone(["4306215837336208023"]) is None


def test_directory_vs_official_website_rules() -> None:
    # Directory links are never treated as official business websites
    assert is_directory_url("https://www.justdial.com/Mumbai/AC-Repair") is True
    assert is_directory_url("https://maps.google.com/place?id=123") is True
    assert is_official_website("https://www.justdial.com/Delhi/Plumber") is False
    assert is_official_website("https://maps.google.com/place") is False

    # Genuine business domains are recognized
    assert is_official_website("https://superdentalsmile.com") is True
    assert is_official_website("http://delhiplumbingservice.in") is True
    assert is_official_website("") is False
    assert is_official_website(None) is False


def test_google_maps_asset_urls_are_not_business_websites() -> None:
    street_view = (
        "https://streetviewpixels-pa.googleapis.com/v1/thumbnail?"
        "panoid=DJn1aTOJcW3nsMFmtFW9vw&cb_client=search.gws-prod.grass&w=80&h=92"
    )
    google_photo = "https://lh3.googleusercontent.com/p/AF1QipM-example=w80-h92"
    assert is_official_website(street_view) is False
    assert is_official_website(google_photo) is False


def test_website_status_rules() -> None:
    # Available only when verified external official domain is found
    assert determine_website_status(official_website_url="https://business.com") == "available"
    # Never claim missing unless explicit trusted source confirms it
    assert (
        determine_website_status(official_website_url=None, explicit_missing_confirmed=False)
        == "unknown"
    )
    assert (
        determine_website_status(official_website_url=None, explicit_missing_confirmed=True)
        == "missing"
    )
    # Inaccessible when network check failed
    assert (
        determine_website_status(official_website_url=None, page_fetch_failed=True)
        == "inaccessible"
    )


def test_address_never_falls_back_to_city() -> None:
    # If the candidate address is just the city name, it must be cleared to None
    assert sanitize_address("Delhi", "Delhi") is None
    assert sanitize_address("Delhi NCR", "Delhi NCR") is None
    assert sanitize_address("Bengaluru", "Bengaluru, India") is None
    assert sanitize_address("None", "Mumbai") is None
    assert sanitize_address("N/A", "Pune") is None

    # Legitimate street address survives
    legit = "Plot 42, Sector 14, Rohini"
    assert sanitize_address(legit, "Delhi") == legit


def test_field_provenance_non_regression() -> None:
    # Schema.org extraction (conf 1.0) must never be overwritten by a directory snippet (conf 0.75)
    existing_schema = {
        "value": "+91 98765 43210",
        "confidence": EXTRACTION_CONFIDENCE["schema.org"],
        "source_type": "website",
    }
    weaker_snippet = FieldEvidence(
        value="+91 11 2233 4455",
        source_url="https://justdial.com/sample",
        source_type="justdial",
        extraction_method="search_snippet",
        checked_at=datetime.now(UTC).isoformat(),
        confidence=EXTRACTION_CONFIDENCE["search_snippet"],
    )
    # Weaker cannot overwrite stronger
    assert should_update_field(existing_schema, weaker_snippet) is False

    # Stronger evidence CAN update weaker evidence
    stronger_schema = FieldEvidence(
        value="+91 98765 43210",
        source_url="https://official.com",
        source_type="website",
        extraction_method="schema.org",
        checked_at=datetime.now(UTC).isoformat(),
        confidence=EXTRACTION_CONFIDENCE["schema.org"],
    )
    assert should_update_field({"value": "+91 0000", "confidence": 0.5}, stronger_schema) is True


def test_deduplication_rules() -> None:
    dummy_owner = uuid.uuid4()
    b1 = Business(
        owner_user_id=dummy_owner,
        name="Apex Dental Clinic",
        normalized_name="apex dental clinic",
        phone="+91 98111 22334",
        normalized_phone="+919811122334",
        website_url="https://apexdental.in",
        normalized_domain="apexdental.in",
        address="Shop 5, Main Market, Rohini Sector 7",
        city="Delhi",
        latitude=28.7041,
        longitude=77.1025,
        website_status="available",
        first_discovered_at=datetime.now(UTC),
    )

    # 1. Matching name + phone -> MATCH
    assert (
        matches_existing_business(
            candidate_name="Apex Dental Clinic",
            candidate_phone="+91 98111 22334",
            candidate_website=None,
            candidate_address=None,
            candidate_lat=None,
            candidate_lon=None,
            existing=b1,
        )
        is True
    )

    # 2. Matching name + domain -> MATCH
    assert (
        matches_existing_business(
            candidate_name="Apex Dental Clinic",
            candidate_phone=None,
            candidate_website="https://apexdental.in/contact",
            candidate_address=None,
            candidate_lat=None,
            candidate_lon=None,
            existing=b1,
        )
        is True
    )

    # 3. Matching name + nearby coordinates (within 100m) -> MATCH
    assert (
        matches_existing_business(
            candidate_name="Apex Dental Clinic",
            candidate_phone=None,
            candidate_website=None,
            candidate_address=None,
            candidate_lat=28.7042,
            candidate_lon=77.1026,
            existing=b1,
        )
        is True
    )

    # 4. Same name BUT different phone/address/domain -> MUST NOT MERGE
    assert (
        matches_existing_business(
            candidate_name="Apex Dental Clinic",
            candidate_phone="+91 88000 99999",
            candidate_website="https://different-apex.com",
            candidate_address="MG Road, Connaught Place",
            candidate_lat=28.6315,
            candidate_lon=77.2167,
            existing=b1,
        )
        is False
    )


def test_scan_planner_generates_variants_and_localities() -> None:
    plan = build_scan_plan(niche="dentists", city="Delhi", country="India")
    assert len(plan.query_variants) >= 3
    assert len(plan.locality_units) >= 3
    assert any("dental" in q.lower() or "dentist" in q.lower() for q in plan.query_variants)
    assert any(u.source_name == "searxng" for u in plan.units)
    assert any(u.source_name == "google_maps" for u in plan.units)
    assert any(u.source_name == "justdial" for u in plan.units)


def test_field_status_and_completeness_rules() -> None:
    # Available fields
    st = build_field_status(
        has_phone=True,
        has_email=False,
        has_website=True,
        has_address=True,
        has_rating=True,
        has_reviews=True,
        page_checked=True,
        page_fetch_failed=False,
    )
    assert st["phone"] == "available"
    assert st["email"] == "not_found_after_public_page_check"
    assert st["website"] == "available"
    assert st["address"] == "available"

    # Inaccessible fetch sets review requirement
    comp = compute_completeness_status(
        name="Test Biz",
        address="Sector 1",
        phone="+91 123",
        email=None,
        website_url=None,
        website_status="inaccessible",
        field_statuses={"website": "inaccessible"},
    )
    assert comp == "needs_review"


# ── 2. Mocked Test Doubles for Fast, Deterministic Integration Tests ─────────


@pytest.fixture(autouse=True)
def mock_scan_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks network adapters so integration tests run in milliseconds without live HTTP calls."""

    async def _mock_searx(self: Any, query: str, locality: str | None = None) -> list[RawCandidate]:
        return [
            RawCandidate(
                name="Alpha Dental Care",
                source_url="https://alphadentalcare.in",
                source_type="website",
                query=query,
                retrieval_time="2026-11-06T00:00:00Z",
                raw_evidence_snippet="Alpha Dental Care official website",
                phone="+91 98111 22334",
                official_website_url="https://alphadentalcare.in",
                metadata={"discovery_source": "searxng"},
            )
        ]

    async def _mock_gmaps(self: Any, query: str, locality: str | None = None) -> list[RawCandidate]:
        return [
            RawCandidate(
                name="Alpha Dental Care",
                source_url="https://www.google.com/maps/place/?q=place_id:ChIJ123",
                source_type="google_maps",
                query=query,
                retrieval_time="2026-11-06T00:00:00Z",
                raw_evidence_snippet="Alpha Dental Care Delhi (4.8 stars)",
                phone="+91 98111 22334",
                address="Plot 10, Sector 12, Dwarka",
                rating=4.8,
                review_count=120,
                official_website_url="https://alphadentalcare.in",
                latitude=28.59,
                longitude=77.06,
                place_id="ChIJ123",
                metadata={"discovery_source": "google_maps"},
            )
        ]

    async def _mock_justdial(
        self: Any, query: str, locality: str | None = None
    ) -> list[RawCandidate]:
        return [
            RawCandidate(
                name="Alpha Dental Care",
                source_url="https://www.justdial.com/Delhi/Alpha-Dental-Care",
                source_type="justdial",
                query=query,
                retrieval_time="2026-11-06T00:00:00Z",
                raw_evidence_snippet="Alpha Dental Care Dwarka Justdial listing",
                phone="+91 98111 22334",
                metadata={"discovery_source": "justdial"},
            )
        ]

    async def _mock_fetch(target_url: str, max_contact_pages: int = 2) -> tuple[Any, list[Any]]:
        return (
            PublicPageFetchResult(
                url=target_url,
                final_url=target_url,
                status="ok",
                status_code=200,
                phone="+91 98111 22334",
                email="contact@alphadentalcare.in",
                address="Plot 10, Sector 12, Dwarka",
                rating=None,
                review_count=None,
                contact_urls=[],
                social_urls=["https://facebook.com/alphadentalcare"],
                extraction_method="schema_org_json_ld",
            ),
            [],
        )

    import app.modules.discovery.scan_service as s_service
    from app.modules.discovery.scan_adapters import (
        DirectoryScanAdapter,
        GoogleLocalScanAdapter,
        SearXNGScanAdapter,
    )

    monkeypatch.setattr(SearXNGScanAdapter, "execute_query", _mock_searx)
    monkeypatch.setattr(GoogleLocalScanAdapter, "execute_query", _mock_gmaps)
    monkeypatch.setattr(DirectoryScanAdapter, "execute_query", _mock_justdial)
    monkeypatch.setattr(s_service, "fetch_candidate_website_and_contact_pages", _mock_fetch)


# ── 3. Authenticated Integration Tests: Scans API Lifecycle ─────────────────


def test_authenticated_scan_lifecycle(
    make_account: Callable[[], Session],
    mock_scan_adapters: None,
) -> None:
    """End-to-end integration test: create scan, execute, poll, verify association & export CSV."""
    account = make_account()

    # 1. Create Scan Run
    create_res = account.api.post(
        "/api/v1/discovery/scans",
        json={"niche": "dentists", "city": "Delhi", "country": "India"},
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert create_res.status_code == 201, create_res.text
    scan_data = create_res.json()
    scan_id = scan_data["id"]
    assert scan_data["niche"] == "dentists"
    assert scan_data["city"] == "Delhi"
    assert len(scan_data["units"]) > 0

    # 2. Poll Scan Run after execution
    poll_res = account.api.get(f"/api/v1/discovery/scans/{scan_id}")
    assert poll_res.status_code == 200
    polled = poll_res.json()
    assert polled["id"] == scan_id
    assert polled["status"] == "completed"
    assert polled["accepted_count"] >= 1
    coverage = polled["source_coverage"]
    assert coverage["searxng"]["queries_run"] > 0
    assert coverage["google_maps"]["candidates_found"] > 0
    assert coverage["justdial"]["candidates_found"] > 0
    assert sum(source["accepted"] for source in coverage.values()) == polled["accepted_count"]
    assert sum(source["duplicates"] for source in coverage.values()) == polled["duplicate_count"]
    assert (
        polled["accepted_count"] + polled["duplicate_count"] + polled["rejected_count"]
        == polled["candidate_count"]
    )

    # 3. Export Scan Leads CSV (Must only contain this scan's leads)
    export_res = account.api.get(f"/api/v1/discovery/scans/{scan_id}/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"].startswith("text/csv")
    csv_text = export_res.text
    assert "Name,Category,Phone,Email,Website URL" in csv_text
    assert "Alpha Dental Care" in csv_text
    assert "Completeness Status" in csv_text


def test_owner_isolation(
    make_account: Callable[[], Session],
    mock_scan_adapters: None,
) -> None:
    """Account B must never see or control Account A's scans."""
    account_a = make_account()
    account_b = make_account()

    res_a = account_a.api.post(
        "/api/v1/discovery/scans",
        json={"niche": "plumbers", "city": "Mumbai", "country": "India"},
        headers={**account_a.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    scan_id_a = res_a.json()["id"]

    # Account B attempts to read A's scan -> 404
    poll_b = account_b.api.get(f"/api/v1/discovery/scans/{scan_id_a}")
    assert poll_b.status_code == 404

    # Account B attempts to cancel A's scan -> 404
    cancel_b = account_b.api.post(
        f"/api/v1/discovery/scans/{scan_id_a}/cancel",
        headers={**account_b.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert cancel_b.status_code == 404

    # Account B attempts to export A's scan -> 404
    export_b = account_b.api.get(f"/api/v1/discovery/scans/{scan_id_a}/export")
    assert export_b.status_code == 404


def test_cancellation_and_resumability(
    make_account: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies cancel sets cancellation_requested and resume resets only incomplete units."""
    account = make_account()

    # Stub execute_scan_run so the scan remains queued/running for cancellation testing
    async def _stub_execute(*, scan_run_id: str) -> str:
        return "running"

    import app.modules.discovery.scan_service as s_service

    monkeypatch.setattr(s_service, "execute_scan_run", _stub_execute)

    # 1. Create scan
    create_res = account.api.post(
        "/api/v1/discovery/scans",
        json={"niche": "electricians", "city": "Bengaluru", "country": "India"},
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert create_res.status_code == 201
    scan_id = create_res.json()["id"]

    # 2. Cancel scan
    cancel_res = account.api.post(
        f"/api/v1/discovery/scans/{scan_id}/cancel",
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancellation_requested"

    # 3. Resume scan
    resume_res = account.api.post(
        f"/api/v1/discovery/scans/{scan_id}/resume",
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    assert resume_res.status_code == 200
    resumed = resume_res.json()
    assert resumed["cancellation_requested"] is False
    assert resumed["retries"] >= 1


def test_no_candidates_returned(
    make_account: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When sources return 0 candidates, scan completes truthfully with 0 accepted."""
    account = make_account()

    async def _mock_empty(self: Any, query: str, locality: str | None = None) -> list[RawCandidate]:
        return []

    from app.modules.discovery.scan_adapters import (
        DirectoryScanAdapter,
        GoogleLocalScanAdapter,
        SearXNGScanAdapter,
    )

    monkeypatch.setattr(SearXNGScanAdapter, "execute_query", _mock_empty)
    monkeypatch.setattr(GoogleLocalScanAdapter, "execute_query", _mock_empty)
    monkeypatch.setattr(DirectoryScanAdapter, "execute_query", _mock_empty)

    create_res = account.api.post(
        "/api/v1/discovery/scans",
        json={"niche": "rare_craft", "city": "RemoteTown", "country": "India"},
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    scan_id = create_res.json()["id"]

    poll_res = account.api.get(f"/api/v1/discovery/scans/{scan_id}")
    assert poll_res.status_code == 200
    polled = poll_res.json()
    assert polled["status"] == "completed"
    assert polled["candidate_count"] == 0
    assert polled["accepted_count"] == 0


def test_failed_source_reporting(
    make_account: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all sources raise errors, scan marks failed with error_summary."""
    account = make_account()

    async def _mock_fail(self: Any, query: str, locality: str | None = None) -> list[RawCandidate]:
        raise RuntimeError("Source timeout or connection refused")

    from app.modules.discovery.scan_adapters import (
        DirectoryScanAdapter,
        GoogleLocalScanAdapter,
        SearXNGScanAdapter,
    )

    monkeypatch.setattr(SearXNGScanAdapter, "execute_query", _mock_fail)
    monkeypatch.setattr(GoogleLocalScanAdapter, "execute_query", _mock_fail)
    monkeypatch.setattr(DirectoryScanAdapter, "execute_query", _mock_fail)

    create_res = account.api.post(
        "/api/v1/discovery/scans",
        json={"niche": "plumbers", "city": "Jaipur", "country": "India"},
        headers={**account.csrf_headers(), "Origin": "http://localhost:3000"},
    )
    scan_id = create_res.json()["id"]

    poll_res = account.api.get(f"/api/v1/discovery/scans/{scan_id}")
    assert poll_res.status_code == 200
    polled = poll_res.json()
    assert polled["status"] == "failed"
    assert polled["error_summary"] is not None


def test_merge_attaches_source_listing_links() -> None:
    """Verifies that listings from Justdial and Google Maps are tagged specifically."""
    dummy_owner = uuid.uuid4()
    biz = Business(
        owner_user_id=dummy_owner,
        name="Reliable Plumbing",
        normalized_name="reliable plumbing",
        city="Delhi",
        website_status="unknown",
        first_discovered_at=datetime.now(UTC),
        enrichment={},
    )

    now_iso = datetime.now(UTC).isoformat()
    # 1. Merge from Justdial
    merge_candidate_into_business(
        biz,
        candidate_name="Reliable Plumbing",
        candidate_phone="+91 98111 22334",
        candidate_email=None,
        candidate_website=None,
        candidate_address="Shop 2, Dwarka Sector 6",
        candidate_city="Delhi",
        candidate_rating=4.5,
        candidate_review_count=18,
        candidate_lat=None,
        candidate_lon=None,
        source_url="https://www.justdial.com/Delhi/Reliable-Plumbing",
        source_type="justdial",
        field_evidence_map={
            "phone": FieldEvidence(
                value="+91 98111 22334",
                source_url="https://www.justdial.com/Delhi/Reliable-Plumbing",
                source_type="justdial",
                extraction_method="structured_directory",
                checked_at=now_iso,
                confidence=0.75,
            )
        },
        is_new=True,
    )

    listings = biz.enrichment["source_listing_urls"]
    assert len(listings) == 1
    assert listings[0]["kind"] == "justdial"
    assert listings[0]["label"] == "Justdial"
    assert biz.enrichment["justdial_url"] == "https://www.justdial.com/Delhi/Reliable-Plumbing"

    # 2. Merge from Google Maps
    merge_candidate_into_business(
        biz,
        candidate_name="Reliable Plumbing",
        candidate_phone="+91 98111 22334",
        candidate_email=None,
        candidate_website="https://reliableplumbingdelhi.in",
        candidate_address="Shop 2, Dwarka Sector 6",
        candidate_city="Delhi",
        candidate_rating=4.7,
        candidate_review_count=42,
        candidate_lat=28.59,
        candidate_lon=77.06,
        source_url="https://www.google.com/maps/place/Reliable+Plumbing",
        source_type="google_maps",
        field_evidence_map={
            "website": FieldEvidence(
                value="https://reliableplumbingdelhi.in",
                source_url="https://www.google.com/maps/place/Reliable+Plumbing",
                source_type="google_maps",
                extraction_method="official_website_link",
                checked_at=now_iso,
                confidence=0.85,
            )
        },
        is_new=False,
    )

    listings_after = biz.enrichment["source_listing_urls"]
    assert len(listings_after) == 2
    has_jd = any(
        item["kind"] == "justdial" and item["label"] == "Justdial"
        for item in listings_after
    )
    has_gm = any(
        item["kind"] == "google_maps" and item["label"] == "Google Maps"
        for item in listings_after
    )
    assert has_jd
    assert has_gm
    assert biz.website_url == "https://reliableplumbingdelhi.in"
    assert biz.website_status == "available"
