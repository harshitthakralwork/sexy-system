from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.notifications.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])

Csrf = Depends(require_csrf_for_state_changes())


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_type: str
    title: str
    message: str
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None
    is_read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.owner_user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

    rows = await session.scalars(stmt)
    return [NotificationOut.model_validate(row) for row in rows]


@router.post("/{notification_id}/read", status_code=204, dependencies=[Csrf])
async def mark_read(
    notification_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> None:
    row = await session.get(Notification, notification_id)
    if row is None or row.owner_user_id != user.id:
        raise NotFoundError("Notification not found")
    row.is_read = True
    await session.flush()


@router.post("/read-all", status_code=204, dependencies=[Csrf])
async def mark_all_read(
    session: AsyncSessionDep,
    user: CurrentUser,
) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.owner_user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await session.flush()
