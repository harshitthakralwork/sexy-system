from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
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
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    UUIDType,
)

# The four revenue evidence classes from the schema. `not_available` exists so
# "we have no evidence" is an explicit, honest state rather than a missing row.
REVENUE_CLASSIFICATIONS = ("verified", "founder_reported", "estimated", "not_available")

STARTUP_STATUSES = ("active", "acquired", "shutdown", "unknown")


class Startup(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A startup entity — the durable record for Startup Intelligence.

    Kept distinct from `businesses` on purpose: a startup is not a lead, and the
    two modules share infrastructure (storage, search, reports) but not rows.
    """

    __tablename__ = "startups"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','acquired','shutdown','unknown')",
            name="ck_startup_status",
        ),
        Index("ix_startup_owner_domain", "owner_user_id", "normalized_domain"),
        Index("ix_startup_owner_industry", "owner_user_id", "industry"),
        Index("ix_startup_owner_stage", "owner_user_id", "funding_stage"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_startups_owner_user_id_users"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    founding_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    # Provenance: which source reported this startup, not a generalised claim.
    source_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_researched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StartupFounder(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "startup_founders"

    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    public_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "startup_products"

    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class StartupPricing(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "startup_pricing"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_startup_pricing_amount_nonnegative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startup_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_name: Mapped[str] = mapped_column(String(150), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    billing_period: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pricing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupRevenueRecord(Base, UUIDPrimaryKeyMixin):
    """One revenue observation, labelled with its evidence class.

    The classification is a CHECK-constrained column, not free text, so a record
    can never claim to be "verified" without passing the vocabulary. An estimate
    must carry a methodology; a `not_available` record must carry no amount.
    """

    __tablename__ = "startup_revenue_records"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('verified','founder_reported','estimated','not_available')",
            name="ck_revenue_classification",
        ),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_revenue_amount_nonnegative"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_revenue_confidence_range",
        ),
    )

    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    revenue_period: Mapped[str | None] = mapped_column(String(30), nullable=True)
    classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_available", server_default=text("'not_available'")
    )
    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupCompetitor(Base, UUIDPrimaryKeyMixin):
    """A directed competitor edge with evidence.

    Self-reference and duplicate pairs are prevented at the database layer, not
    just in code, because a competitor graph with loops or repeats is silently
    wrong in exactly the ways a research tool must not be.
    """

    __tablename__ = "startup_competitors"
    __table_args__ = (
        CheckConstraint(
            "startup_id <> competitor_startup_id", name="ck_competitor_no_self_reference"
        ),
        Index(
            "ix_competitor_pair",
            "startup_id",
            "competitor_startup_id",
            unique=True,
        ),
    )

    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupResearchRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "startup_research_records"

    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_type: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_references: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    researched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StartupWatchlist(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "startup_watchlists"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_startup_watchlists_owner_user_id_users"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class StartupWatchlistItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "startup_watchlist_items"
    __table_args__ = (
        Index("ix_watchlist_item_pair", "watchlist_id", "startup_id", unique=True),
    )

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("startup_watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
