from __future__ import annotations

import io
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.modules.discovery.public_fetch import PublicPageFetchResult, fetch_public_page
from app.modules.social.connectors import SearxngSocialAdapter
from app.modules.verified_prospecting.models import VerifiedProspectingLead, VerifiedProspectingRun
from app.modules.verified_prospecting.schemas import WebProspectingIn

MAX_OSM_XML_BYTES = 25 * 1024 * 1024
MAX_OSM_RECORDS = 5_000


def _score(
    *,
    website_status: str,
    phone: str | None,
    email: str | None,
    rating: float | None,
    reviews: int | None,
    city_match: bool,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    # The new engine never guesses that a business lacks a website. A proven
    # website is still useful context, but absence of a field remains unknown.
    if phone:
        score += 25
        reasons.append("Public phone on source page")
    if email:
        score += 25
        reasons.append("Public email on source page")
    if rating is not None and rating >= 4:
        score += 15
        reasons.append(f"Public rating {rating:.1f}")
    if reviews is not None and reviews >= 20:
        score += 15
        reasons.append(f"{reviews} public reviews")
    if city_match:
        score += 10
        reasons.append("Matches selected city")
    if website_status == "unknown":
        reasons.append("Website status not verified")
    return min(score, 100), reasons


def _run_adapter(settings: Settings) -> SearxngSocialAdapter:
    return SearxngSocialAdapter(
        settings.searxng_base_url,
        user_agent=settings.social_user_agent,
        timeout_seconds=settings.searxng_timeout_seconds,
        results_per_page=settings.searxng_results_per_page,
    )


async def _set_run(session: AsyncSession, run: VerifiedProspectingRun, **values: Any) -> None:
    for name, value in values.items():
        setattr(run, name, value)
    await session.commit()


async def _cancelled(session: AsyncSession, run: VerifiedProspectingRun) -> bool:
    await session.refresh(run)
    return run.cancellation_requested


async def _store_page_lead(
    session: AsyncSession,
    *,
    run: VerifiedProspectingRun,
    source_url: str,
    fetched: PublicPageFetchResult,
) -> bool:
    name = fetched.business_name or fetched.title
    if not name:
        return False
    existing = await session.scalar(
        select(VerifiedProspectingLead.id).where(
            VerifiedProspectingLead.run_id == run.id,
            VerifiedProspectingLead.source_url == source_url,
        )
    )
    if existing:
        return False
    website_url = fetched.website_url
    website_status = "has_website" if website_url else "unknown"
    score, reasons = _score(
        website_status=website_status,
        phone=fetched.phone,
        email=fetched.email,
        rating=fetched.rating,
        reviews=fetched.review_count,
        city_match=run.city.casefold() in (fetched.address or "").casefold(),
    )
    session.add(
        VerifiedProspectingLead(
            run_id=run.id,
            name=name[:300],
            city=run.city,
            source_type="web_index",
            source_url=source_url,
            website_url=website_url,
            website_status=website_status,
            public_phone=fetched.phone,
            public_email=fetched.email,
            address=fetched.address,
            rating=fetched.rating,
            review_count=fetched.review_count,
            potential_score=score,
            score_reasons=reasons,
            evidence={
                "source_url": source_url,
                "final_url": fetched.final_url,
                "extraction_method": fetched.extraction_method,
                "captured_at": datetime.now(UTC).isoformat(),
                "notes": fetched.notes,
            },
        )
    )
    return True


async def execute_web_run(run_id: uuid.UUID) -> None:
    """Run one bounded SearXNG + public-page pass in its own session.

    It intentionally does not use or mutate the legacy discovery or business
    records, allowing this path to be evaluated independently.
    """
    async with session_scope() as session:
        run = await session.get(VerifiedProspectingRun, run_id)
        if run is None or run.cancellation_requested:
            return
        await _set_run(
            session,
            run,
            status="running",
            stage="Searching public web index",
            started_at=datetime.now(UTC),
            progress_percent=5,
        )
        settings = get_settings()
        adapter = _run_adapter(settings)
        try:
            results = await adapter.search(
                {"q": f"{run.niche} {run.city}", "kind": "keyword", "limit": run.max_candidates}
            )
        except Exception as exc:  # noqa: BLE001 - source failures are represented on the run, not hidden
            await _set_run(
                session,
                run,
                status="failed",
                stage="Web index unavailable",
                error_summary=type(exc).__name__,
                completed_at=datetime.now(UTC),
                progress_percent=100,
            )
            return
        finally:
            await adapter.aclose()

        candidates = [result.content_url for result in results if result.content_url][
            : run.max_candidates
        ]
        await _set_run(
            session,
            run,
            candidate_count=len(candidates),
            stage="Reading public business pages",
            progress_percent=15,
        )
        saved = 0
        failed = 0
        for index, source_url in enumerate(candidates, start=1):
            if await _cancelled(session, run):
                await _set_run(
                    session,
                    run,
                    status="cancelled",
                    stage="Cancelled",
                    completed_at=datetime.now(UTC),
                    progress_percent=min(99, 15 + int(index * 80 / max(1, len(candidates)))),
                )
                return
            try:
                fetched = await fetch_public_page(source_url)
                if fetched.status == "ok" and await _store_page_lead(
                    session, run=run, source_url=source_url, fetched=fetched
                ):
                    saved += 1
            except Exception:  # noqa: BLE001 - a single public page must not make the entire run fail
                failed += 1
            progress = min(95, 15 + int(index * 80 / max(1, len(candidates))))
            await _set_run(
                session,
                run,
                saved_count=saved,
                failed_count=failed,
                progress_percent=progress,
                stage=f"Verifying public pages ({index}/{len(candidates)})",
            )

        await _set_run(
            session,
            run,
            status="partial" if failed else "completed",
            stage="Finished",
            saved_count=saved,
            failed_count=failed,
            progress_percent=100,
            completed_at=datetime.now(UTC),
            error_summary=(f"{failed} public pages could not be read" if failed else None),
        )


def _osm_tags(element: ET.Element) -> dict[str, str]:
    return {
        str(tag.attrib.get("k")): str(tag.attrib.get("v"))
        for tag in element.findall("tag")
        if tag.attrib.get("k") and tag.attrib.get("v")
    }


def _osm_is_business(tags: dict[str, str]) -> bool:
    return bool(tags.get("name")) and any(
        key in tags for key in ("shop", "amenity", "craft", "office", "tourism")
    )


async def execute_osm_xml_import(run_id: uuid.UUID, raw_xml: bytes) -> None:
    """Import a user-supplied small OSM XML extract, never a remote OSM API."""
    async with session_scope() as session:
        run = await session.get(VerifiedProspectingRun, run_id)
        if run is None or run.cancellation_requested:
            return
        await _set_run(
            session,
            run,
            status="running",
            stage="Reading OSM city extract",
            started_at=datetime.now(UTC),
            progress_percent=5,
        )
        if (
            len(raw_xml) > MAX_OSM_XML_BYTES
            or b"<!DOCTYPE" in raw_xml.upper()
            or b"<!ENTITY" in raw_xml.upper()
        ):
            await _set_run(
                session,
                run,
                status="failed",
                stage="OSM import refused",
                error_summary="OSM XML exceeds limit or contains an unsafe declaration",
                completed_at=datetime.now(UTC),
                progress_percent=100,
            )
            return
        saved = 0
        total = 0
        try:
            for _event, element in ET.iterparse(io.BytesIO(raw_xml), events=("end",)):
                if element.tag not in {"node", "way"}:
                    continue
                tags = _osm_tags(element)
                if not _osm_is_business(tags):
                    element.clear()
                    continue
                total += 1
                if total > MAX_OSM_RECORDS or await _cancelled(session, run):
                    await _set_run(
                        session,
                        run,
                        status="cancelled" if run.cancellation_requested else "partial",
                        stage="OSM import stopped at safe record limit",
                        saved_count=saved,
                        candidate_count=total,
                        completed_at=datetime.now(UTC),
                        progress_percent=100,
                    )
                    return
                source_url = (
                    f"https://www.openstreetmap.org/{element.tag}/{element.attrib.get('id', '')}"
                )
                existing = await session.scalar(
                    select(VerifiedProspectingLead.id).where(
                        VerifiedProspectingLead.run_id == run.id,
                        VerifiedProspectingLead.source_url == source_url,
                    )
                )
                if not existing:
                    website = tags.get("website") or tags.get("contact:website")
                    phone = tags.get("phone") or tags.get("contact:phone")
                    email = tags.get("email") or tags.get("contact:email")
                    score, reasons = _score(
                        website_status="has_website" if website else "unknown",
                        phone=phone,
                        email=email,
                        rating=None,
                        reviews=None,
                        city_match=True,
                    )
                    session.add(
                        VerifiedProspectingLead(
                            run_id=run.id,
                            name=tags["name"][:300],
                            city=run.city,
                            source_type="osm_extract",
                            source_url=source_url,
                            website_url=website,
                            website_status="has_website" if website else "unknown",
                            public_phone=phone,
                            public_email=email,
                            address=" ".join(
                                filter(
                                    None,
                                    [
                                        tags.get("addr:housenumber"),
                                        tags.get("addr:street"),
                                        tags.get("addr:postcode"),
                                    ],
                                )
                            )
                            or None,
                            latitude=float(element.attrib["lat"])
                            if element.tag == "node" and element.attrib.get("lat")
                            else None,
                            longitude=float(element.attrib["lon"])
                            if element.tag == "node" and element.attrib.get("lon")
                            else None,
                            potential_score=score,
                            score_reasons=reasons,
                            evidence={
                                "source_url": source_url,
                                "extraction_method": "osm_xml_tags",
                                "captured_at": datetime.now(UTC).isoformat(),
                                "tags": tags,
                            },
                        )
                    )
                    saved += 1
                element.clear()
                if total % 25 == 0:
                    await _set_run(
                        session,
                        run,
                        candidate_count=total,
                        saved_count=saved,
                        progress_percent=min(95, 5 + total // 50),
                        stage=f"Importing OSM records ({total})",
                    )
        except ET.ParseError as exc:
            await _set_run(
                session,
                run,
                status="failed",
                stage="OSM XML could not be read",
                error_summary=str(exc)[:300],
                completed_at=datetime.now(UTC),
                progress_percent=100,
            )
            return
        await _set_run(
            session,
            run,
            status="completed",
            stage="Finished",
            candidate_count=total,
            saved_count=saved,
            progress_percent=100,
            completed_at=datetime.now(UTC),
        )


async def create_web_run(
    session: AsyncSession, owner_user_id: uuid.UUID, payload: WebProspectingIn
) -> VerifiedProspectingRun:
    run = VerifiedProspectingRun(
        owner_user_id=owner_user_id,
        niche=payload.niche.strip(),
        city=payload.city.strip(),
        source_kind="web_index",
        max_candidates=payload.max_candidates,
    )
    session.add(run)
    await session.flush()
    return run


async def list_leads(
    session: AsyncSession, *, run_id: uuid.UUID, owner_user_id: uuid.UUID
) -> tuple[list[VerifiedProspectingLead], int]:
    owns = await session.scalar(
        select(VerifiedProspectingRun.id).where(
            VerifiedProspectingRun.id == run_id,
            VerifiedProspectingRun.owner_user_id == owner_user_id,
        )
    )
    if not owns:
        return [], 0
    rows = list(
        (
            await session.scalars(
                select(VerifiedProspectingLead)
                .where(VerifiedProspectingLead.run_id == run_id)
                .order_by(
                    VerifiedProspectingLead.potential_score.desc(),
                    VerifiedProspectingLead.created_at.desc(),
                )
            )
        ).all()
    )
    return rows, len(rows)
