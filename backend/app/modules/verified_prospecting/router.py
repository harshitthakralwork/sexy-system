from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile, status
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.verified_prospecting import service
from app.modules.verified_prospecting.models import VerifiedProspectingRun
from app.modules.verified_prospecting.schemas import (
    VerifiedLeadListOut,
    VerifiedRunOut,
    WebProspectingIn,
)

router = APIRouter(prefix="/verified-prospecting", tags=["verified prospecting"])
Csrf = Depends(require_csrf_for_state_changes())
RUN_RULE = RateLimitRule(max_attempts=10, window_seconds=300)


async def _run_or_404(
    session: AsyncSessionDep, run_id: uuid.UUID, owner_user_id: uuid.UUID
) -> VerifiedProspectingRun:
    run = await session.scalar(
        select(VerifiedProspectingRun).where(
            VerifiedProspectingRun.id == run_id,
            VerifiedProspectingRun.owner_user_id == owner_user_id,
        )
    )
    if run is None:
        raise NotFoundError("Verified prospecting run was not found")
    return run


@router.post(
    "/runs", response_model=VerifiedRunOut, status_code=status.HTTP_201_CREATED, dependencies=[Csrf]
)
async def create_web_run(
    request: Request,
    payload: WebProspectingIn,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> VerifiedProspectingRun:
    allowed, _retry_after = get_rate_limiter().check(
        "verified_web_prospecting", str(user.id), RUN_RULE
    )
    if not allowed:
        raise ValidationFailedError("Too many prospecting runs. Wait before starting another one.")
    run = await service.create_web_run(session, user.id, payload)
    background.add_task(service.execute_web_run, run.id)
    await record_audit(
        session,
        action="verified_prospecting.web_run_created",
        owner_user_id=user.id,
        entity_type="verified_prospecting_run",
        entity_id=run.id,
        ip_address=client_ip(request),
        metadata={"niche": run.niche, "city": run.city},
    )
    return run


@router.post(
    "/osm-import",
    response_model=VerifiedRunOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Csrf],
)
async def create_osm_import(
    request: Request,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    city: str = Form(..., min_length=2, max_length=160),
    niche: str = Form(default="local businesses", max_length=160),
    file: UploadFile = File(...),
) -> VerifiedProspectingRun:
    if not file.filename or not file.filename.lower().endswith(".osm"):
        raise ValidationFailedError(
            "Upload a small .osm XML city extract. PBF is intentionally not accepted "
            "in this local importer."
        )
    raw_xml = await file.read(service.MAX_OSM_XML_BYTES + 1)
    if len(raw_xml) > service.MAX_OSM_XML_BYTES:
        raise ValidationFailedError(
            "OSM XML extract is too large. Export a smaller city area (maximum 25 MB)."
        )
    run = VerifiedProspectingRun(
        owner_user_id=user.id,
        niche=niche.strip() or "local businesses",
        city=city.strip(),
        source_kind="osm_extract",
        max_candidates=service.MAX_OSM_RECORDS,
    )
    session.add(run)
    await session.flush()
    background.add_task(service.execute_osm_xml_import, run.id, raw_xml)
    await record_audit(
        session,
        action="verified_prospecting.osm_import_created",
        owner_user_id=user.id,
        entity_type="verified_prospecting_run",
        entity_id=run.id,
        ip_address=client_ip(request),
        metadata={"city": run.city, "filename": file.filename, "bytes": len(raw_xml)},
    )
    return run


@router.get("/runs", response_model=list[VerifiedRunOut])
async def list_runs(session: AsyncSessionDep, user: CurrentUser) -> list[VerifiedProspectingRun]:
    return list(
        (
            await session.scalars(
                select(VerifiedProspectingRun)
                .where(VerifiedProspectingRun.owner_user_id == user.id)
                .order_by(VerifiedProspectingRun.created_at.desc())
                .limit(50)
            )
        ).all()
    )


@router.get("/runs/{run_id}", response_model=VerifiedRunOut)
async def get_run(
    run_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> VerifiedProspectingRun:
    return await _run_or_404(session, run_id, user.id)


@router.post("/runs/{run_id}/cancel", response_model=VerifiedRunOut, dependencies=[Csrf])
async def cancel_run(
    run_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> VerifiedProspectingRun:
    run = await _run_or_404(session, run_id, user.id)
    if run.status in {"completed", "partial", "failed", "cancelled"}:
        return run
    run.cancellation_requested = True
    run.stage = "Cancelling after the current public page"
    return run


@router.get("/runs/{run_id}/leads", response_model=VerifiedLeadListOut)
async def get_leads(
    run_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> VerifiedLeadListOut:
    await _run_or_404(session, run_id, user.id)
    items, total = await service.list_leads(session, run_id=run_id, owner_user_id=user.id)
    return VerifiedLeadListOut(items=items, total=total)
