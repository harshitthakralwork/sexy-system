from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import (
    JSONType,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    UUIDType,
)

SOCIAL_CONTENT_TYPES = ("post", "comment", "profile", "other")
PLATFORM_HEALTH_STATUSES = ("working", "degraded", "failed", "unknown")


class SocialPlatform(Base, UUIDPrimaryKeyMixin):
    """One social platform, described by what its permitted access actually allows.

    `capabilities` and `limitations` exist so the UI can state what a platform
    can and cannot do instead of implying parity. `is_enabled` is false for every
    platform whose permitted public access is absent or key-gated, so the honest
    default is "restricted" rather than "available" (PRD §5.3, architecture §15).
    """

    __tablename__ = "social_platforms"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    capabilities: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    limitations: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    health_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SocialProfile(Base, UUIDPrimaryKeyMixin):
    """A public social account, captured during a user's research run.

    `owner_user_id` is a deliberate addition to `database-schema.md` §14.2: a
    profile surfaced by one user's private search must not leak to another user,
    so ownership follows the same rule as every other collected record (PRD §17).
    """

    __tablename__ = "social_profiles"
    __table_args__ = (
        Index(
            "ix_social_profile_owner_platform_external",
            "owner_user_id",
            "platform_id",
            "external_id",
            unique=True,
        ),
    )

    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("social_platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_metadata: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_researched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SocialContent(Base, UUIDPrimaryKeyMixin):
    """One collected post, comment or profile reference with attribution.

    `owner_user_id` and `research_query_id` are additions to §14.3: without
    them, collected content has no owner and no link to the configured search
    that produced it, which breaks both the two-user isolation proof and the
    "configure a search, see its results" loop.
    """

    __tablename__ = "social_content"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('post','comment','profile','other')",
            name="ck_social_content_type",
        ),
        Index(
            "ix_social_content_owner_platform_external",
            "owner_user_id",
            "platform_id",
            "external_id",
            unique=True,
        ),
    )

    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("social_platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    research_query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("social_research_queries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("social_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="post", server_default=text("'post'")
    )
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engagement_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialResearchQuery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A configured social search: platform + a validated query shape.

    The run-status columns are additions to §14.4 so the UI can state "ran at
    X, failed with Y" instead of implying a configured search produced results.
    """

    __tablename__ = "social_research_queries"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("social_platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
