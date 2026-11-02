from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import (
    JSONType,
    OwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    UUIDType,
)

SOCIAL_CONTENT_TYPES = ("post", "comment", "profile", "other")
PLATFORM_HEALTH_STATUSES = ("working", "degraded", "failed", "unknown")

# --- Social & Demand Intelligence Engine (extension) ------------------------
# Track types are the two independent intelligence tracks the engine must keep
# separate in configuration, classification and filtering while sharing storage.
TRACK_TYPES = ("demand", "business")
# Retrieval status is the honest answer to "how much of this did we actually get".
# It is not interchangeable with classification: a snippet can be classified
# without its full content ever having been retrieved.
RETRIEVAL_STATUSES = (
    "retrieved",
    "snippet_only",
    "indexed_snippet",
    "public_page_retrieved",
    "user_provided_url",
    "inaccessible",
    "unsupported",
)
CLASSIFICATION_METHODS = ("rule", "ai", "manual")
RUN_STATUSES = ("pending", "running", "completed", "completed_with_warnings", "failed", "cancelled")
TRIGGER_TYPES = ("manual", "scheduled")


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
        CheckConstraint(
            "track_type IN ('demand','business')",
            name="ck_social_content_track_type",
        ),
        CheckConstraint(
            "retrieval_status IN ('retrieved','snippet_only','indexed_snippet',"
            "'public_page_retrieved','user_provided_url','inaccessible','unsupported')",
            name="ck_social_content_retrieval_status",
        ),
        CheckConstraint(
            "classification_method IN ('rule','ai','manual')",
            name="ck_social_content_classification_method",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="ck_social_content_confidence_range",
        ),
        Index(
            "ix_social_content_owner_platform_external",
            "owner_user_id",
            "platform_id",
            "external_id",
            unique=True,
        ),
        Index("ix_social_content_owner_track", "owner_user_id", "track_type"),
        Index("ix_social_content_dedup_fingerprint", "dedup_fingerprint"),
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

    # Intelligence columns added by the Social & Demand Intelligence Engine. Every
    # one is nullable so previously collected rows stay valid; classification is
    # derived, not assumed, and retrieval_status is kept separate from it.
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("social_search_tracks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    track_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(150), nullable=True)
    retrieval_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    classification_method: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default="rule", server_default=text("'rule'")
    )
    classification_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_terms: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    evidence: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    positive_signals: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    negative_signals: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    dedup_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_attribution: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SocialSearchTrack(Base, OwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """A configured, schedulable intelligence search — one of the two tracks.

    A track fans out across the platforms it selects. The query vocabulary is
    deliberately richer than a single keyword list (phrases, exclusions,
    hashtags) because a Demand track ("looking for a web agency") and a Business
    track ("new SaaS launch") are different products and must not be collapsed.
    """

    __tablename__ = "social_search_tracks"
    __table_args__ = (
        CheckConstraint("track_type IN ('demand','business')", name="ck_social_track_type"),
        CheckConstraint("max_results_per_run >= 1", name="ck_social_track_max_results"),
        Index("ix_social_track_owner_type", "owner_user_id", "track_type"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    track_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="demand", server_default=text("'demand'")
    )
    keywords: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    exact_phrases: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    excluded_terms: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    hashtags: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    platforms: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(150), nullable=True)
    date_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Per-platform extras a track needs beyond the shared vocabulary: feed URLs for
    # RSS, subreddit names for Reddit, an instance host for Mastodon, etc.
    source_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    frequency_config: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    max_results_per_run: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default=text("50")
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialDiscoveryRun(Base, OwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """One auditable execution of a track across its sources.

    The counts are kept separate on purpose — results_returned, stored_new and
    duplicates are not interchangeable, and conflating them is how a repeated
    run silently inflates a total. A run whose source failed still records what
    happened rather than disappearing.
    """

    __tablename__ = "social_discovery_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','completed_with_warnings','failed',"
            "'cancelled')",
            name="ck_social_run_status",
        ),
        CheckConstraint(
            "trigger_type IN ('manual','scheduled')",
            name="ck_social_run_trigger",
        ),
        Index("ix_social_run_owner_track_time", "owner_user_id", "track_id", "created_at"),
    )

    track_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("social_search_tracks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default=text("'manual'")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sources_attempted: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    queries_attempted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    results_returned: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    stored_new: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duplicates: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    review_flagged: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    classification_counts: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SocialSavedItem(Base, OwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """An opportunity or company the user chose to keep, with a note and tags.

    Saved items reference collected content rather than copying it, so a record's
    provenance and classification stay single-sourced; the note/tags are the
    user's own annotations and never rewrite the underlying evidence.
    """

    __tablename__ = "social_saved_items"
    __table_args__ = (
        Index("ix_social_saved_owner_content", "owner_user_id", "content_id", unique=True),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("social_content.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    converted_business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )


class SocialClassificationHistory(Base, UUIDPrimaryKeyMixin):
    """One reclassification event, kept when a rule version or a human changes a call.

    History is appended, never overwritten: "why did this say Vendor Search last
    week and Agency Search now" is exactly the question an evidence-first product
    has to be able to answer.
    """

    __tablename__ = "social_classification_history"

    content_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("social_content.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    classification_method: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
