from __future__ import annotations

import asyncio
import copy
import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.discovery.deduplication import (
    matches_existing_business,
    merge_candidate_into_business,
)
from app.modules.discovery.provenance import (
    EXTRACTION_CONFIDENCE,
    FieldEvidence,
    determine_website_status,
    is_official_website,
    sanitize_address,
)
from app.modules.discovery.scan_adapters import (
    DirectoryScanAdapter,
    GoogleLocalScanAdapter,
    RawCandidate,
    SearXNGScanAdapter,
    fetch_candidate_website_and_contact_pages,
)
from app.modules.discovery.scan_models import LocalScanBusiness, LocalScanRun, LocalScanUnit
from app.modules.discovery.scan_planner import build_scan_plan
from app.shared.normalization import normalize_domain, normalize_email, normalize_phone


def build_field_status(
    *,
    has_phone: bool,
    has_email: bool,
    has_website: bool,
    has_address: bool,
    has_rating: bool,
    has_reviews: bool,
    page_checked: bool,
    page_fetch_failed: bool,
    is_missing_confirmed: bool = False,
) -> dict[str, str]:
    """Generates explicit verification statuses for each field without claiming absent data."""
    if is_missing_confirmed:
        website_st = "missing"
    elif has_website:
        website_st = "available"
    elif page_checked:
        website_st = "not_found_after_public_page_check"
    elif page_fetch_failed:
        website_st = "inaccessible"
    else:
        website_st = "not_verified"

    def contact_st(present: bool) -> str:
        if present:
            return "available"
        if page_checked:
            return "not_found_after_public_page_check"
        if page_fetch_failed:
            return "inaccessible"
        return "not_verified"

    return {
        "name": "available",
        "phone": contact_st(has_phone),
        "email": contact_st(has_email),
        "website": website_st,
        "address": "available" if has_address else "not_verified",
        "rating": "available" if has_rating else "not_verified",
        "review_count": "available" if has_reviews else "not_verified",
    }


def compute_completeness_status(
    *,
    name: str,
    address: str | None,
    phone: str | None,
    email: str | None,
    website_url: str | None,
    website_status: str,
    field_statuses: dict[str, str],
) -> str:
    """Truthful completeness calculation grounded in verified evidence."""
    if any(st == "inaccessible" for st in field_statuses.values()):
        return "needs_review"
    has_contact = bool(phone or email)
    has_website_state = bool(website_url or website_status == "missing")
    if name and address and has_contact and has_website_state:
        return "complete"
    return "partial"


async def create_scan_run(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    niche: str,
    city: str,
    country: str = "India",
) -> LocalScanRun:
    """Plans and persists a durable, multi-unit Scan Run."""
    clean_niche = niche.strip()
    clean_city = city.strip()
    clean_country = country.strip() or "India"

    plan = build_scan_plan(niche=clean_niche, city=clean_city, country=clean_country)

    initial_coverage = {
        "searxng": {
            "queries_run": 0,
            "pages_checked": 0,
            "candidates_found": 0,
            "accepted": 0,
            "duplicates": 0,
            "errors": 0,
        },
        "justdial": {
            "queries_run": 0,
            "pages_checked": 0,
            "candidates_found": 0,
            "accepted": 0,
            "duplicates": 0,
            "errors": 0,
        },
        "google_maps": {
            "queries_run": 0,
            "pages_checked": 0,
            "candidates_found": 0,
            "accepted": 0,
            "duplicates": 0,
            "errors": 0,
        },
        "website": {
            "queries_run": 0,
            "pages_checked": 0,
            "candidates_found": 0,
            "accepted": 0,
            "duplicates": 0,
            "errors": 0,
        },
    }

    scan_run = LocalScanRun(
        owner_user_id=owner_user_id,
        niche=clean_niche,
        city=clean_city,
        country=clean_country,
        query_variants=plan.query_variants,
        locality_units=plan.locality_units,
        status="queued",
        stage="planning",
        progress_percent=1.0,
        source_coverage=initial_coverage,
    )
    session.add(scan_run)
    await session.flush()

    for p_unit in plan.units:
        unit = LocalScanUnit(
            scan_run_id=scan_run.id,
            source_name=p_unit.source_name,
            unit_kind=p_unit.unit_kind,
            query_or_url=p_unit.query_or_url,
            locality=p_unit.locality,
            status="queued",
            execution_metadata=p_unit.execution_metadata,
        )
        session.add(unit)

    await session.commit()
    return scan_run


async def cancel_scan_run(
    session: AsyncSession,
    scan_run_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> bool:
    """Requests graceful cancellation. The active worker marks units cancelled and finalizes."""
    stmt = (
        update(LocalScanRun)
        .where(
            LocalScanRun.id == scan_run_id,
            LocalScanRun.owner_user_id == owner_user_id,
            LocalScanRun.status.in_(("queued", "planning", "running")),
        )
        .values(cancellation_requested=True)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.rowcount > 0


async def resume_scan_run(
    session: AsyncSession,
    scan_run_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> bool:
    """Resumes failed or cancelled units without re-executing already completed units."""
    scan = await session.get(LocalScanRun, scan_run_id)
    if not scan or scan.owner_user_id != owner_user_id:
        return False

    # Reset only uncompleted/failed units back to queued
    await session.execute(
        update(LocalScanUnit)
        .where(
            LocalScanUnit.scan_run_id == scan_run_id,
            LocalScanUnit.status.in_(("failed", "cancelled")),
        )
        .values(
            status="queued",
            error_message=None,
            started_at=None,
            completed_at=None,
        )
    )

    scan.status = "queued"
    scan.stage = "planning"
    scan.cancellation_requested = False
    scan.error_summary = None
    scan.retries += 1
    await session.commit()
    return True


async def execute_scan_run(*, scan_run_id: str) -> str:
    """Background runner for a durable Scan Run with real stage transitions
    and monotonic progress.
    """
    try:
        run_uuid = uuid.UUID(scan_run_id)
    except ValueError:
        return "failed"

    searx_adapter = SearXNGScanAdapter()
    gmaps_adapter = GoogleLocalScanAdapter()
    dir_adapter = DirectoryScanAdapter()

    # 1. Atomic claim to guarantee only one worker runs this scan
    async with session_scope() as session:
        claim_stmt = (
            update(LocalScanRun)
            .where(
                LocalScanRun.id == run_uuid,
                LocalScanRun.status.in_(("queued", "planning")),
            )
            .values(
                status="running",
                stage="source_discovery",
                started_at=func.coalesce(LocalScanRun.started_at, datetime.now(UTC)),
                progress_percent=func.greatest(LocalScanRun.progress_percent, 5.0),
            )
        )
        claim_res = await session.execute(claim_stmt)
        await session.commit()
        if claim_res.rowcount == 0:
            return "ignored"

    try:
        async with session_scope() as session:
            scan = await session.get(LocalScanRun, run_uuid)
            if not scan:
                return "not_found"

            # Check if cancellation was requested before units
            if scan.cancellation_requested:
                scan.status = "cancelled"
                scan.stage = "cancelled"
                await session.execute(
                    update(LocalScanUnit)
                    .where(
                        LocalScanUnit.scan_run_id == run_uuid,
                        LocalScanUnit.status.in_(("queued", "running")),
                    )
                    .values(status="cancelled", completed_at=datetime.now(UTC))
                )
                await session.commit()
                return "cancelled"

            # Load only queued units (never repeat completed units)
            units_stmt = (
                select(LocalScanUnit)
                .where(
                    LocalScanUnit.scan_run_id == run_uuid,
                    LocalScanUnit.status.in_(("queued", "failed")),
                )
                .order_by(LocalScanUnit.created_at)
            )
            units = list((await session.scalars(units_stmt)).all())
            total_units = len(units) or 1
            # JSON columns do not track mutations inside nested dictionaries.
            # Work on a deep copy and assign another fresh copy before every
            # commit so progress and source counters are actually persisted.
            coverage = copy.deepcopy(scan.source_coverage or {})

            candidates: list[RawCandidate] = []
            semaphore = asyncio.Semaphore(2)

            # ── Stage 2: Source Discovery ──────────────────────────────────────
            for idx, unit in enumerate(units, start=1):
                await session.refresh(scan, attribute_names=["cancellation_requested", "status"])
                if scan.cancellation_requested or scan.status == "cancelled":
                    scan.status = "cancelled"
                    scan.stage = "cancelled"
                    unit.status = "cancelled"
                    await session.execute(
                        update(LocalScanUnit)
                        .where(
                            LocalScanUnit.scan_run_id == run_uuid,
                            LocalScanUnit.status == "queued",
                        )
                        .values(status="cancelled", completed_at=datetime.now(UTC))
                    )
                    await session.commit()
                    return "cancelled"

                unit.status = "running"
                unit.started_at = datetime.now(UTC)
                await session.commit()

                src_cov = coverage.setdefault(
                    unit.source_name,
                    {
                        "queries_run": 0,
                        "pages_checked": 0,
                        "candidates_found": 0,
                        "accepted": 0,
                        "duplicates": 0,
                        "errors": 0,
                    },
                )
                src_cov["queries_run"] += 1

                unit_results: list[RawCandidate] = []
                err: str | None = None

                try:
                    async with semaphore:
                        if unit.source_name == "searxng":
                            unit_results = await searx_adapter.execute_query(
                                unit.query_or_url, unit.locality
                            )
                        elif unit.source_name == "google_maps":
                            unit_results = await gmaps_adapter.execute_query(
                                unit.query_or_url, unit.locality
                            )
                        elif unit.source_name == "justdial":
                            unit_results = await dir_adapter.execute_query(
                                unit.query_or_url, unit.locality
                            )
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    src_cov["errors"] += 1

                unit.status = "completed" if not err else "failed"
                unit.error_message = err
                unit.completed_at = datetime.now(UTC)
                unit.candidates_found = len(unit_results)
                src_cov["candidates_found"] += len(unit_results)

                candidates.extend(unit_results)

                # Monotonic progress (5% -> 45% during discovery)
                progress_val = 5.0 + ((idx / total_units) * 40.0)
                scan.progress_percent = max(
                    float(scan.progress_percent or 0), round(progress_val, 2)
                )
                scan.candidate_count = len(candidates)
                scan.source_coverage = copy.deepcopy(coverage)
                await session.commit()

            # ── Check for total source failure ────────────────────────────────
            all_units_failed = len(units) > 0 and all(u.status == "failed" for u in units)
            if all_units_failed:
                scan.status = "failed"
                scan.stage = "failed"
                scan.error_summary = "All scan sources failed or could not be reached."
                await session.commit()
                return "failed"

            # ── Stage 3 & 4: Page Verification & Contact-Page Checks ───────────
            await session.refresh(scan, attribute_names=["cancellation_requested"])
            if scan.cancellation_requested:
                scan.status = "cancelled"
                scan.stage = "cancelled"
                await session.commit()
                return "cancelled"

            scan.stage = "page_verification"
            scan.progress_percent = max(float(scan.progress_percent or 0), 45.0)
            await session.commit()

            # Deduplicate raw candidate list by source_url before fetching
            unique_candidates: dict[str, RawCandidate] = {}
            for c in candidates:
                if c.source_url not in unique_candidates:
                    unique_candidates[c.source_url] = c
                    continue
                duplicate_source = str(
                    c.metadata.get("discovery_source") or c.source_type
                )
                duplicate_cov = coverage.setdefault(
                    duplicate_source,
                    {
                        "queries_run": 0,
                        "pages_checked": 0,
                        "candidates_found": 0,
                        "accepted": 0,
                        "duplicates": 0,
                        "errors": 0,
                    },
                )
                duplicate_cov["duplicates"] += 1

            cand_list = list(unique_candidates.values())
            raw_duplicate_count = len(candidates) - len(cand_list)
            total_cands = len(cand_list) or 1
            fetched_evidence_map: dict[str, tuple[Any, list[Any], bool]] = {}

            web_cov = coverage.setdefault(
                "website",
                {
                    "queries_run": 0,
                    "pages_checked": 0,
                    "candidates_found": 0,
                    "accepted": 0,
                    "duplicates": 0,
                    "errors": 0,
                },
            )

            scan.stage = "contact_page_checks"
            await session.commit()

            # Verify all candidates with accessible websites using bounded concurrency
            fetch_semaphore = asyncio.Semaphore(3)
            for c_idx, cand in enumerate(cand_list, start=1):
                await session.refresh(scan, attribute_names=["cancellation_requested"])
                if scan.cancellation_requested:
                    scan.status = "cancelled"
                    scan.stage = "cancelled"
                    await session.commit()
                    return "cancelled"

                target_to_fetch = cand.official_website_url or (
                    cand.source_url if cand.source_type == "website" else None
                )
                if target_to_fetch and target_to_fetch.startswith("http"):
                    try:
                        async with fetch_semaphore:
                            main_res, contact_res = await fetch_candidate_website_and_contact_pages(
                                target_to_fetch, max_contact_pages=2
                            )
                            fetched_evidence_map[cand.source_url] = (main_res, contact_res, True)
                            web_cov["pages_checked"] += 1 + len(contact_res)
                    except Exception:  # noqa: BLE001
                        web_cov["errors"] += 1
                        fetched_evidence_map[cand.source_url] = (None, [], False)

                # Monotonic progress (45% -> 75% during verification)
                v_progress = 45.0 + ((c_idx / total_cands) * 30.0)
                scan.progress_percent = max(float(scan.progress_percent or 0), round(v_progress, 2))
                scan.source_coverage = copy.deepcopy(coverage)
                await session.commit()

            # ── Stage 5 & 6: Deduplication & Saving ─────────────────────────────
            scan.stage = "deduplication"
            scan.progress_percent = max(float(scan.progress_percent or 0), 75.0)
            await session.commit()

            existing_businesses_stmt = select(Business).where(
                Business.owner_user_id == scan.owner_user_id,
                Business.city.ilike(scan.city),
                Business.deleted_at.is_(None),
            )
            existing_businesses = list((await session.scalars(existing_businesses_stmt)).all())

            accepted_count = 0
            duplicate_count = raw_duplicate_count
            rejected_count = 0
            now_iso = datetime.now(UTC).isoformat()

            scan.stage = "saving"
            await session.commit()

            for cand in cand_list:
                if len(cand.name) < 2:
                    rejected_count += 1
                    continue

                fetch_info = fetched_evidence_map.get(cand.source_url)
                main_fetch = fetch_info[0] if fetch_info else None
                contact_fetches = fetch_info[1] if fetch_info else []
                page_checked = bool(main_fetch and main_fetch.status == "ok")
                page_fetch_failed = bool(fetch_info and not fetch_info[2])

                phone = cand.phone
                email = cand.email
                address = sanitize_address(cand.address, scan.city)
                website = cand.official_website_url
                # A listing URL is evidence about a business, not its website.
                # Never promote the same URL into both fields, even when an
                # upstream adapter mislabeled the candidate.
                if (
                    website
                    and cand.source_url
                    and website.rstrip("/") == cand.source_url.rstrip("/")
                ):
                    website = None
                rating = cand.rating
                review_count = cand.review_count
                social_links: list[str] = []

                field_evidence_map: dict[str, FieldEvidence] = {}

                # Primary candidate evidence
                if phone:
                    field_evidence_map["phone"] = FieldEvidence(
                        value=phone,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method=(
                            "structured_directory"
                            if cand.source_type != "website"
                            else "visible_text_official"
                        ),
                        checked_at=now_iso,
                        confidence=(
                            EXTRACTION_CONFIDENCE["structured_directory"]
                            if cand.source_type != "website"
                            else EXTRACTION_CONFIDENCE["visible_text_official"]
                        ),
                    )
                if email:
                    field_evidence_map["email"] = FieldEvidence(
                        value=email,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method=(
                            "structured_directory"
                            if cand.source_type != "website"
                            else "visible_text_official"
                        ),
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["structured_directory"],
                    )
                if address:
                    field_evidence_map["address"] = FieldEvidence(
                        value=address,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method="structured_directory",
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["structured_directory"],
                    )
                if website and is_official_website(website):
                    field_evidence_map["website"] = FieldEvidence(
                        value=website,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method="official_website_link",
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["visible_text_official"],
                    )
                if rating is not None:
                    field_evidence_map["rating"] = FieldEvidence(
                        value=rating,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method="structured_directory",
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["structured_directory"],
                    )
                if review_count is not None:
                    field_evidence_map["review_count"] = FieldEvidence(
                        value=review_count,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        extraction_method="structured_directory",
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["structured_directory"],
                    )

                # Enrich with main page fetch (schema.org JSON-LD has highest confidence: 1.0)
                if main_fetch and main_fetch.status == "ok":
                    is_schema = main_fetch.extraction_method == "schema_org_json_ld"
                    conf = (
                        EXTRACTION_CONFIDENCE["schema.org"]
                        if is_schema
                        else EXTRACTION_CONFIDENCE["visible_text_official"]
                    )

                    if main_fetch.phone:
                        phone = main_fetch.phone
                        field_evidence_map["phone"] = FieldEvidence(
                            value=phone,
                            source_url=main_fetch.final_url,
                            source_type="website",
                            extraction_method="schema.org"
                            if is_schema
                            else "visible_text_official",
                            checked_at=now_iso,
                            confidence=conf,
                        )
                    if main_fetch.email:
                        email = main_fetch.email
                        field_evidence_map["email"] = FieldEvidence(
                            value=email,
                            source_url=main_fetch.final_url,
                            source_type="website",
                            extraction_method="schema.org"
                            if is_schema
                            else "visible_text_official",
                            checked_at=now_iso,
                            confidence=conf,
                        )
                    clean_fetch_addr = sanitize_address(main_fetch.address, scan.city)
                    if clean_fetch_addr:
                        address = clean_fetch_addr
                        field_evidence_map["address"] = FieldEvidence(
                            value=address,
                            source_url=main_fetch.final_url,
                            source_type="website",
                            extraction_method="schema.org"
                            if is_schema
                            else "visible_text_official",
                            checked_at=now_iso,
                            confidence=conf,
                        )
                    if main_fetch.rating is not None:
                        rating = main_fetch.rating
                        field_evidence_map["rating"] = FieldEvidence(
                            value=rating,
                            source_url=main_fetch.final_url,
                            source_type="website",
                            extraction_method="schema.org"
                            if is_schema
                            else "visible_text_official",
                            checked_at=now_iso,
                            confidence=conf,
                        )
                    if main_fetch.review_count is not None:
                        review_count = main_fetch.review_count
                        field_evidence_map["review_count"] = FieldEvidence(
                            value=review_count,
                            source_url=main_fetch.final_url,
                            source_type="website",
                            extraction_method="schema.org"
                            if is_schema
                            else "visible_text_official",
                            checked_at=now_iso,
                            confidence=conf,
                        )
                    if main_fetch.social_urls:
                        social_links.extend(main_fetch.social_urls)

                # Enrich with contact pages (confidence: 0.95)
                for c_res in contact_fetches:
                    if c_res.phone and "phone" not in field_evidence_map:
                        phone = c_res.phone
                        field_evidence_map["phone"] = FieldEvidence(
                            value=phone,
                            source_url=c_res.final_url,
                            source_type="website",
                            extraction_method="official_contact_page",
                            checked_at=now_iso,
                            confidence=EXTRACTION_CONFIDENCE["official_contact_page"],
                        )
                    if c_res.email and "email" not in field_evidence_map:
                        email = c_res.email
                        field_evidence_map["email"] = FieldEvidence(
                            value=email,
                            source_url=c_res.final_url,
                            source_type="website",
                            extraction_method="official_contact_page",
                            checked_at=now_iso,
                            confidence=EXTRACTION_CONFIDENCE["official_contact_page"],
                        )
                    clean_c_addr = sanitize_address(c_res.address, scan.city)
                    if clean_c_addr and "address" not in field_evidence_map:
                        address = clean_c_addr
                        field_evidence_map["address"] = FieldEvidence(
                            value=address,
                            source_url=c_res.final_url,
                            source_type="website",
                            extraction_method="official_contact_page",
                            checked_at=now_iso,
                            confidence=EXTRACTION_CONFIDENCE["official_contact_page"],
                        )
                    if c_res.social_urls:
                        social_links.extend(c_res.social_urls)

                if social_links:
                    field_evidence_map["social_links"] = FieldEvidence(
                        value=list(dict.fromkeys(social_links)),
                        source_url=cand.source_url,
                        source_type="website",
                        extraction_method="contact_page_links",
                        checked_at=now_iso,
                        confidence=EXTRACTION_CONFIDENCE["official_contact_page"],
                    )

                field_statuses = build_field_status(
                    has_phone=bool(phone),
                    has_email=bool(email),
                    has_website=bool(website and is_official_website(website)),
                    has_address=bool(address),
                    has_rating=bool(rating is not None),
                    has_reviews=bool(review_count is not None),
                    page_checked=page_checked,
                    page_fetch_failed=page_fetch_failed,
                )
                completeness = compute_completeness_status(
                    name=cand.name.strip(),
                    address=address,
                    phone=phone,
                    email=email,
                    website_url=website,
                    website_status=determine_website_status(
                        official_website_url=website, sources_checked=True
                    ),
                    field_statuses=field_statuses,
                )

                # Deduplication matching against existing records
                matched_business: Business | None = None
                for ex in existing_businesses:
                    if matches_existing_business(
                        candidate_name=cand.name,
                        candidate_phone=phone,
                        candidate_website=website,
                        candidate_address=address,
                        candidate_lat=cand.latitude,
                        candidate_lon=cand.longitude,
                        existing=ex,
                    ):
                        matched_business = ex
                        break

                target_biz: Business
                discovery_source = str(
                    cand.metadata.get("discovery_source") or cand.source_type
                )
                discovery_cov = coverage.setdefault(
                    discovery_source,
                    {
                        "queries_run": 0,
                        "pages_checked": 0,
                        "candidates_found": 0,
                        "accepted": 0,
                        "duplicates": 0,
                        "errors": 0,
                    },
                )
                if matched_business:
                    merge_candidate_into_business(
                        matched_business,
                        candidate_name=cand.name,
                        candidate_phone=phone,
                        candidate_email=email,
                        candidate_website=website,
                        candidate_address=address,
                        candidate_city=scan.city,
                        candidate_rating=rating,
                        candidate_review_count=review_count,
                        candidate_lat=cand.latitude,
                        candidate_lon=cand.longitude,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        field_evidence_map=field_evidence_map,
                        is_new=False,
                    )
                    target_biz = matched_business
                    duplicate_count += 1
                    discovery_cov["duplicates"] += 1
                else:
                    new_biz = Business(
                        owner_user_id=scan.owner_user_id,
                        name=cand.name.strip(),
                        normalized_name=cand.name.strip().casefold(),
                        primary_category=scan.niche,
                        city=scan.city,
                        address=address,
                        website_url=website,
                        normalized_domain=normalize_domain(website) if website else None,
                        website_status=determine_website_status(
                            official_website_url=website, sources_checked=True
                        ),
                        phone=phone,
                        normalized_phone=normalize_phone(phone) if phone else None,
                        email=email,
                        normalized_email=normalize_email(email) if email else None,
                        rating=rating,
                        review_count=review_count,
                        latitude=cand.latitude,
                        longitude=cand.longitude,
                        lifecycle_status="active",
                        first_discovered_at=datetime.now(UTC),
                        enrichment={},
                    )
                    merge_candidate_into_business(
                        new_biz,
                        candidate_name=cand.name,
                        candidate_phone=phone,
                        candidate_email=email,
                        candidate_website=website,
                        candidate_address=address,
                        candidate_city=scan.city,
                        candidate_rating=rating,
                        candidate_review_count=review_count,
                        candidate_lat=cand.latitude,
                        candidate_lon=cand.longitude,
                        source_url=cand.source_url,
                        source_type=cand.source_type,
                        field_evidence_map=field_evidence_map,
                        is_new=True,
                    )
                    session.add(new_biz)
                    await session.flush()
                    existing_businesses.append(new_biz)
                    target_biz = new_biz
                    accepted_count += 1
                    discovery_cov["accepted"] += 1

                # Update enrichment with explicit field statuses and scan association
                enr = dict(target_biz.enrichment or {})
                enr["field_status"] = field_statuses
                enr["completeness_status"] = completeness
                scan_ids = list(enr.get("scan_ids", []))
                if str(scan.id) not in scan_ids:
                    scan_ids.append(str(scan.id))
                enr["scan_ids"] = scan_ids
                target_biz.enrichment = enr

                # Associate scan with business in local_scan_businesses table
                assoc_stmt = select(LocalScanBusiness).where(
                    LocalScanBusiness.scan_run_id == scan.id,
                    LocalScanBusiness.business_id == target_biz.id,
                )
                existing_assoc = await session.scalar(assoc_stmt)
                if not existing_assoc:
                    session.add(
                        LocalScanBusiness(
                            scan_run_id=scan.id,
                            business_id=target_biz.id,
                        )
                    )

            scan.accepted_count = accepted_count
            scan.duplicate_count = duplicate_count
            scan.rejected_count = rejected_count

            # Mark completed
            scan.status = "completed"
            scan.stage = "completed"
            scan.progress_percent = 100.0
            scan.completed_at = datetime.now(UTC)
            scan.source_coverage = copy.deepcopy(coverage)
            await session.commit()

            return "completed"

    except Exception as exc:
        async with session_scope() as session:
            err_scan = await session.get(LocalScanRun, run_uuid)
            if err_scan and err_scan.status == "running":
                err_scan.status = "failed"
                err_scan.stage = "failed"
                err_scan.error_summary = f"Worker encountered error: {exc}"
                await session.commit()
        raise


def generate_scan_csv(businesses: list[Business]) -> str:
    """Produces CSV export with field evidence URLs and completeness status."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Name",
            "Category",
            "Phone",
            "Email",
            "Website URL",
            "Website Status",
            "Address",
            "City",
            "Rating",
            "Review Count",
            "Completeness Status",
            "Source Listing URLs",
            "Field Evidence Summary",
        ]
    )
    for b in businesses:
        enr = b.enrichment or {}
        listings = enr.get("source_listing_urls", [])
        listing_str = " | ".join(
            f"{item.get('label', 'Source')}: {item.get('url', '')}"
            for item in listings
            if isinstance(item, dict)
        )

        prov = enr.get("field_provenance", {})
        prov_summary = " | ".join(
            f"{k}: {v.get('value')} (via {v.get('extraction_method')} from {v.get('source_url')})"
            for k, v in prov.items()
            if isinstance(v, dict) and v.get("value")
        )

        writer.writerow(
            [
                b.name,
                b.primary_category or "",
                b.phone or "",
                b.email or "",
                b.website_url or "",
                b.website_status,
                b.address or "",
                b.city or "",
                b.rating or "",
                b.review_count or "",
                enr.get("completeness_status", "partial"),
                listing_str,
                prov_summary,
            ]
        )
    return output.getvalue()
