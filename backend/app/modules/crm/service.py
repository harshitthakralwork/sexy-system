from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.businesses.models import Business
from app.modules.crm.models import (
    DEFAULT_STAGES,
    TERMINAL_STAGES,
    CrmActivity,
    CrmBusinessRecord,
    CrmPipeline,
    CrmStage,
    CrmStageHistory,
)

DEFAULT_PIPELINE_NAME = "Leads pipeline"


async def ensure_default_pipeline(session: AsyncSession, owner_user_id: uuid.UUID) -> CrmPipeline:
    """Create the default pipeline and its 12 stages once per owner.

    Idempotent by lookup rather than by insert-and-catch, because two concurrent
    calls creating two pipelines would split one user's board in half.
    """
    pipeline = await session.scalar(
        select(CrmPipeline).where(
            CrmPipeline.owner_user_id == owner_user_id,
            CrmPipeline.is_default.is_(True),
        )
    )
    if pipeline is not None:
        return pipeline

    pipeline = CrmPipeline(owner_user_id=owner_user_id, name=DEFAULT_PIPELINE_NAME, is_default=True)
    session.add(pipeline)
    await session.flush()

    for position, name in enumerate(DEFAULT_STAGES, start=1):
        session.add(
            CrmStage(
                pipeline_id=pipeline.id,
                name=name,
                position=position,
                is_terminal=name in TERMINAL_STAGES,
                is_active=True,
            )
        )
    await session.flush()
    return pipeline


async def stage_by_name(
    session: AsyncSession, pipeline_id: uuid.UUID, name: str
) -> CrmStage | None:
    return await session.scalar(
        select(CrmStage).where(CrmStage.pipeline_id == pipeline_id, CrmStage.name == name)
    )


async def crm_record_for(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> tuple[CrmBusinessRecord, CrmPipeline]:
    """The business's row in its owner's default pipeline, created if absent."""
    pipeline = await ensure_default_pipeline(session, owner_user_id)
    record = await session.scalar(
        select(CrmBusinessRecord).where(
            CrmBusinessRecord.business_id == business_id,
            CrmBusinessRecord.pipeline_id == pipeline.id,
        )
    )
    if record is not None:
        return record, pipeline

    entry_stage = await stage_by_name(session, pipeline.id, "New")
    if entry_stage is None:  # pragma: no cover - seeded above
        raise RuntimeError("Default pipeline has no 'New' stage")
    record = CrmBusinessRecord(
        business_id=business_id,
        pipeline_id=pipeline.id,
        stage_id=entry_stage.id,
        owner_user_id=owner_user_id,
    )
    session.add(record)
    await session.flush()
    session.add(
        CrmStageHistory(
            crm_record_id=record.id,
            previous_stage_id=None,
            new_stage_id=entry_stage.id,
            changed_at=datetime.now(UTC),
            change_reason="Created from business record",
        )
    )
    return record, pipeline


async def move_stage(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    stage_name: str,
    reason: str | None = None,
    activity_title: str | None = None,
) -> CrmBusinessRecord:
    """Change stage with history and an activity entry.

    Stage history is written here rather than at each call site: conversion
    analytics read `crm_stage_history`, so a path that moves a card without
    recording it would silently understate the pipeline.
    """
    record, pipeline = await crm_record_for(
        session, owner_user_id=owner_user_id, business_id=business_id
    )
    target = await stage_by_name(session, pipeline.id, stage_name)
    if target is None:
        raise ValueError(f"Unknown CRM stage '{stage_name}'")
    if target.id == record.stage_id:
        return record

    previous_stage_id = record.stage_id
    record.stage_id = target.id
    await session.flush()
    now = datetime.now(UTC)
    session.add(
        CrmStageHistory(
            crm_record_id=record.id,
            previous_stage_id=previous_stage_id,
            new_stage_id=target.id,
            changed_at=now,
            change_reason=reason,
        )
    )
    session.add(
        CrmActivity(
            business_id=business_id,
            crm_record_id=record.id,
            owner_user_id=owner_user_id,
            activity_type="stage_change",
            title=activity_title or f"Moved to {stage_name}",
            description=reason,
            occurred_at=now,
        )
    )
    await session.flush()
    return record


async def list_pipelines(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> list[CrmPipeline]:
    """Every pipeline the owner has, ordered default-first."""
    return list(
        await session.scalars(
            select(CrmPipeline)
            .where(CrmPipeline.owner_user_id == owner_user_id)
            .order_by(CrmPipeline.is_default.desc(), CrmPipeline.created_at)
        )
    )


async def stages_for(session: AsyncSession, pipeline_id: uuid.UUID) -> list[CrmStage]:
    return list(
        await session.scalars(
            select(CrmStage)
            .where(CrmStage.pipeline_id == pipeline_id)
            .order_by(CrmStage.position)
        )
    )


async def list_board_cards(
    session: AsyncSession, *, owner_user_id: uuid.UUID, pipeline_id: uuid.UUID
) -> list[CrmBusinessRecord]:
    """The cards in one pipeline, joined to their business and stage.

    Ownership is enforced on the record and the business alike, so a record can
    never drag in a business that belongs to someone else.
    """
    return list(
        await session.scalars(
            select(CrmBusinessRecord)
            .join(Business, Business.id == CrmBusinessRecord.business_id)
            .where(
                CrmBusinessRecord.owner_user_id == owner_user_id,
                CrmBusinessRecord.pipeline_id == pipeline_id,
                Business.deleted_at.is_(None),
            )
            .order_by(CrmBusinessRecord.updated_at.desc())
        )
    )


async def create_stage(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    name: str,
    color: str | None = None,
    position: int | None = None,
) -> CrmStage:
    """Add a stage to the owner's default pipeline.

    Position defaults to the end of the board. Duplicate names are refused, not
    merged: two stages that read identically are how a card ends up lost.
    """
    pipeline = await ensure_default_pipeline(session, owner_user_id)
    existing = await stage_by_name(session, pipeline.id, name)
    if existing is not None:
        raise ValueError(f"A stage named '{name}' already exists")
    if position is None:
        last = await session.scalar(
            select(func.max(CrmStage.position)).where(CrmStage.pipeline_id == pipeline.id)
        )
        position = int(last or 0) + 1
    stage = CrmStage(
        pipeline_id=pipeline.id,
        name=name,
        position=position,
        color=color,
        is_terminal=False,
        is_active=True,
    )
    session.add(stage)
    await session.flush()
    return stage


async def update_stage(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    stage_id: uuid.UUID,
    name: str | None = None,
    color: str | None = None,
    is_active: bool | None = None,
) -> CrmStage:
    """Rename or recolour a stage. Ownership is checked through the pipeline."""
    stage = await session.get(CrmStage, stage_id)
    if stage is None:
        raise LookupError("Stage not found")
    pipeline = await session.get(CrmPipeline, stage.pipeline_id)
    if pipeline is None or pipeline.owner_user_id != owner_user_id:
        raise LookupError("Stage not found")
    if name is not None and name != stage.name:
        clash = await stage_by_name(session, pipeline.id, name)
        if clash is not None and clash.id != stage.id:
            raise ValueError(f"A stage named '{name}' already exists")
        stage.name = name
    if color is not None:
        stage.color = color
    if is_active is not None:
        stage.is_active = is_active
    await session.flush()
    return stage


async def list_activities(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CrmActivity], int]:
    """Activity feed, newest first, optionally scoped to one business."""
    statement = select(CrmActivity).where(CrmActivity.owner_user_id == owner_user_id)
    if business_id is not None:
        statement = statement.where(CrmActivity.business_id == business_id)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.scalars(
            statement.order_by(CrmActivity.occurred_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)
