from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.businesses.models import Business
from app.modules.crm import service
from app.modules.crm.schemas import (
    ActivityListOut,
    ActivityOut,
    BoardCardOut,
    BoardOut,
    PipelineOut,
    StageCreateIn,
    StageOut,
    StageUpdateIn,
)

router = APIRouter(prefix="/crm", tags=["crm"])

Csrf = Depends(require_csrf_for_state_changes())


@router.get("/pipelines", response_model=list[PipelineOut])
async def list_pipelines(session: AsyncSessionDep, user: CurrentUser) -> list[PipelineOut]:
    await service.ensure_default_pipeline(session, user.id)
    pipelines = await service.list_pipelines(session, user.id)
    output: list[PipelineOut] = []
    for pipeline in pipelines:
        stages = await service.stages_for(session, pipeline.id)
        output.append(
            PipelineOut(
                id=pipeline.id,
                name=pipeline.name,
                is_default=pipeline.is_default,
                stages=[StageOut.model_validate(stage) for stage in stages],
            )
        )
    return output


@router.get("/board", response_model=BoardOut)
async def board(session: AsyncSessionDep, user: CurrentUser) -> BoardOut:
    """The default pipeline as a board: its stages plus the cards in each."""
    pipeline = await service.ensure_default_pipeline(session, user.id)
    stages = await service.stages_for(session, pipeline.id)
    records = await service.list_board_cards(
        session, owner_user_id=user.id, pipeline_id=pipeline.id
    )

    stage_names = {stage.id: stage.name for stage in stages}
    business_ids = [record.business_id for record in records]
    businesses = {
        row.id: row
        for row in (
            await session.scalars(select(Business).where(Business.id.in_(business_ids)))
        ).all()
        if business_ids
    }
    cards = [
        BoardCardOut(
            business_id=record.business_id,
            name=(
                businesses[record.business_id].name
                if record.business_id in businesses
                else "Unknown business"
            ),
            primary_category=(
                businesses[record.business_id].primary_category
                if record.business_id in businesses
                else None
            ),
            city=businesses[record.business_id].city if record.business_id in businesses else None,
            website_status=(
                businesses[record.business_id].website_status
                if record.business_id in businesses
                else "unknown"
            ),
            stage_id=record.stage_id,
            stage_name=stage_names.get(record.stage_id, "Unknown"),
            next_follow_up_at=record.next_follow_up_at,
        )
        for record in records
    ]
    return BoardOut(stages=[StageOut.model_validate(stage) for stage in stages], cards=cards)


@router.get("/stages", response_model=list[StageOut])
async def list_stages(session: AsyncSessionDep, user: CurrentUser) -> list[StageOut]:
    pipeline = await service.ensure_default_pipeline(session, user.id)
    stages = await service.stages_for(session, pipeline.id)
    return [StageOut.model_validate(stage) for stage in stages]


@router.post("/stages", response_model=StageOut, status_code=201, dependencies=[Csrf])
async def create_stage(
    request: Request,
    payload: StageCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> StageOut:
    try:
        stage = await service.create_stage(
            session,
            owner_user_id=user.id,
            name=payload.name,
            color=payload.color,
            position=payload.position,
        )
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    await record_audit(
        session,
        action="crm.stage_create",
        owner_user_id=user.id,
        entity_type="crm_stage",
        entity_id=stage.id,
        ip_address=client_ip(request),
        metadata={"name": stage.name},
    )
    return StageOut.model_validate(stage)


@router.patch("/stages/{stage_id}", response_model=StageOut, dependencies=[Csrf])
async def update_stage(
    stage_id: uuid.UUID,
    payload: StageUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> StageOut:
    try:
        stage = await service.update_stage(
            session,
            owner_user_id=user.id,
            stage_id=stage_id,
            name=payload.name,
            color=payload.color,
            is_active=payload.is_active,
        )
    except LookupError as exc:
        raise NotFoundError("Stage not found") from exc
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return StageOut.model_validate(stage)


@router.get("/activities", response_model=ActivityListOut)
async def list_activities(
    session: AsyncSessionDep,
    user: CurrentUser,
    business_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ActivityListOut:
    rows, total = await service.list_activities(
        session, owner_user_id=user.id, business_id=business_id, limit=limit, offset=offset
    )
    return ActivityListOut(
        items=[ActivityOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
