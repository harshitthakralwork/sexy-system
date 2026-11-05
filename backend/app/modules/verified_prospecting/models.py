from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType


class VerifiedProspectingRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A separate evidence-first run. It never writes into ``businesses``."""

    __tablename__ = "verified_prospecting_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')",
            name="ck_verified_prospecting_run_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_verified_prospecting_run_progress",
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    niche: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    source_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="web_index", server_default=text("'web_index'")
    )
    max_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, default=25, server_default=text("25")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default=text("'queued'"), index=True
    )
    stage: Mapped[str] = mapped_column(
        String(160), nullable=False, default="Queued", server_default=text("'Queued'")
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    saved_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cancellation_requested: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerifiedProspectingLead(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "verified_prospecting_leads"
    __table_args__ = (
        UniqueConstraint("run_id", "source_url", name="uq_verified_prospecting_lead_run_source"),
        CheckConstraint(
            "website_status IN ('has_website', 'unknown')",
            name="ck_verified_prospecting_lead_website_status",
        ),
        CheckConstraint(
            "potential_score >= 0 AND potential_score <= 100",
            name="ck_verified_prospecting_lead_score",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("verified_prospecting_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    public_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    public_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    potential_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    score_reasons: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    evidence: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
