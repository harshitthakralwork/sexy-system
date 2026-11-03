from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

JSONType = JSONB(astext_type=None)
UUIDType = UUID(as_uuid=True)


def utcnow() -> datetime:
    """Timezone-aware UTC. Storage is always UTC; conversion happens in the UI."""
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OwnedMixin:
    """Every user-facing table carries an owner.

    Single-user today; this is what makes multi-user a non-breaking change.

    The reference to `users` is declared here rather than left to a convention:
    an owner column without the foreign key lets a row outlive the account that
    created it, and nothing in the application would notice.
    """

    @declared_attr
    def owner_user_id(cls: Any) -> Mapped[uuid.UUID]:
        table_name = getattr(cls, "__tablename__", "owned")
        return mapped_column(
            UUIDType,
            ForeignKey("users.id", name=f"fk_{table_name}_owner_user_id_users"),
            nullable=False,
            index=True,
        )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
