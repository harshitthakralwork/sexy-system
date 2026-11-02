from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
