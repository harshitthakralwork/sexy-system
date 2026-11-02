from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.services_catalog.models import Service  # noqa: F401  referenced below
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

DEFAULT_STAGES = (
    "New",
    "Researched",
    "Qualified",
    "Shortlisted",
    "Contacted",
    "Follow-up",
    "Interested",
    "Meeting Scheduled",
    "Proposal Sent",
    "Won",
    "Lost",
    "Archived",
)

TERMINAL_STAGES = {"Won", "Lost", "Archived"}


class CrmPipeline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crm_pipelines"
    __table_args__ = (Index("ix_pipeline_owner_default", "owner_user_id", "is_default"),)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class CrmStage(Base, UUIDPrimaryKeyMixin):
    """Stages are rows, not enum values, so a user can rename or add one."""

    __tablename__ = "crm_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "position", name="uq_stage_position_per_pipeline"),
    )

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_terminal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class CrmBusinessRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A business's position in a pipeline."""

    __tablename__ = "crm_business_records"
    __table_args__ = (
        UniqueConstraint("business_id", "pipeline_id", name="uq_business_per_pipeline"),
        Index("ix_crm_record_follow_up", "owner_user_id", "next_follow_up_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("crm_stages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    assigned_service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CrmStageHistory(Base):
    """Every stage movement is recorded, including why.

    Conversion analytics read from here rather than trusting a current-stage
    snapshot, so "how long was this in Proposal Sent" stays answerable.
    """

    __tablename__ = "crm_stage_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    crm_record_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("crm_business_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("crm_stages.id", ondelete="SET NULL"), nullable=True
    )
    new_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("crm_stages.id", ondelete="RESTRICT"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CrmActivity(Base):
    __tablename__ = "crm_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    crm_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("crm_business_records.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Tag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("owner_user_id", "name", name="uq_tag_name_per_owner"),)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BusinessTag(Base):
    """The composite primary key *is* the uniqueness rule here.

    A separate UniqueConstraint over the same two columns was removed after
    `alembic check` flagged drift: autogenerate folds it into the key at table
    creation but keeps reporting it as missing, which would have left a
    migration that never converges.
    """

    __tablename__ = "business_tags"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class BusinessNote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "business_notes"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
