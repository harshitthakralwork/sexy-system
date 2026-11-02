from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

OPPORTUNITY_STATUSES = ("unqualified", "candidate", "qualified", "shortlisted", "rejected")


class Service(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A sellable service. Configurable, never hardcoded — the catalog is data.

    ``is_active`` lets a service be retired without rewriting the opportunities
    and scores already computed against it.
    """

    __tablename__ = "services"
    __table_args__ = (Index("ix_service_owner_slug", "owner_user_id", "slug", unique=True),)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class ServiceProfile(Base, UUIDPrimaryKeyMixin):
    """An ideal-customer profile: the criteria plus the version that produced a score.

    ``version`` increments instead of mutating in place, so a score stored three
    months ago can still be re-derived exactly.
    """

    __tablename__ = "service_profiles"
    __table_args__ = (
        CheckConstraint(
            "qualification_threshold >= 0 AND qualification_threshold <= 100",
            name="ck_profile_threshold",
        ),
        Index("ix_profile_service_active_version", "service_id", "is_active", "version"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    criteria: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    exclusion_rules: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    qualification_threshold: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=60, server_default=text("60")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScoringRuleRecord(Base, UUIDPrimaryKeyMixin):
    """One weighted signal inside a profile version."""

    __tablename__ = "scoring_rules"
    __table_args__ = (
        CheckConstraint("weight >= 0", name="ck_rule_weight_nonnegative"),
        CheckConstraint(
            "operator IN ('gte','lte','eq','neq','exists','missing','contains','in')",
            name="ck_rule_operator",
        ),
        Index("ix_rule_profile_active", "service_profile_id", "is_active"),
    )

    service_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("service_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_name: Mapped[str] = mapped_column(String(150), nullable=False)
    signal_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=1)
    operator: Mapped[str] = mapped_column(
        String(30), nullable=False, default="exists", server_default=text("'exists'")
    )
    # JSONB holds any JSON value, so a threshold can be a number, string, boolean
    # or list — whatever the operator compares against. Typed as `dict` originally
    # by mistake; the scoring engine compares against scalars.
    threshold: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class BusinessOpportunity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One business evaluated against one service.

    A business can hold several of these at once, which is why scoring is
    per-service rather than a single "lead value" number.
    """

    __tablename__ = "business_opportunities"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_opportunity_score_range"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100", name="ck_opportunity_confidence_range"
        ),
        CheckConstraint(
            "status IN ('unqualified','candidate','qualified','shortlisted','rejected')",
            name="ck_opportunity_status",
        ),
        Index("ix_opportunity_business_service", "business_id", "service_id"),
        Index("ix_opportunity_owner_score_status", "owner_user_id", "score", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("service_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unqualified",
        server_default=text("'unqualified'"),
        index=True,
    )
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_information: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OpportunityEvidence(Base):
    """The reason behind a score contribution.

    Without this table a score is an opinion; with it, the user can check the
    claim, see the source URL, and disagree.
    """

    __tablename__ = "opportunity_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("business_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scoring_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("scoring_rules.id", ondelete="SET NULL"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_value: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    score_contribution: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=0)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
