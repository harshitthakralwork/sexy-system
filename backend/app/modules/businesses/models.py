from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base import (
    JSONType,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    UUIDType,
)

WEBSITE_STATUSES = ("available", "missing", "inaccessible", "unknown")
LIFECYCLE_STATUSES = ("active", "archived", "deleted")
VERIFICATION_STATUSES = ("verified", "unverified", "invalid", "unknown")


class Business(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A normalised business entity — the durable record.

    ``website_status`` distinguishes "we looked and it is absent" from "we
    could not reach it" from "we have not checked", because treating those as
    one state would turn an unverified guess into an opportunity score.
    """

    __tablename__ = "businesses"
    __table_args__ = (
        CheckConstraint(
            "website_status IN ('available','missing','inaccessible','unknown')",
            name="ck_business_website_status",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active','archived','deleted')",
            name="ck_business_lifecycle_status",
        ),
        Index("ix_business_owner_domain", "owner_user_id", "normalized_domain"),
        Index("ix_business_owner_location", "owner_user_id", "country", "city"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_category: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)

    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    website_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default=text("'unknown'")
    )

    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)

    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    lifecycle_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", server_default=text("'active'"), index=True
    )
    enrichment: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    first_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_researched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    contacts: Mapped[list[BusinessContact]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class BusinessContact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A public contact belonging to a business, with its own verification state.

    Extraction is not verification: a scraped address stays ``unverified`` until
    something independently supports it.
    """

    __tablename__ = "business_contacts"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('verified','unverified','invalid','unknown')",
            name="ck_contact_verification_status",
        ),
        Index("ix_contact_business_email", "business_id", "normalized_email"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    contact_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default=text("'unknown'"), index=True
    )
    verification_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Provenance for this specific field, not for the business as a whole.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True, index=True)
    verification_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    business: Mapped[Business] = relationship(back_populates="contacts")


class BusinessSocialProfile(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "business_social_profiles"
    __table_args__ = (
        Index("ix_social_profile_business_platform", "business_id", "platform", unique=True),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_url: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BusinessCategory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "business_categories"
    __table_args__ = (Index("ix_category_slug", "slug", unique=True),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("business_categories.id", ondelete="SET NULL"), nullable=True
    )


class BusinessCategoryLink(Base):
    """Many categories per business, each attributable to the source that said so."""

    __tablename__ = "business_category_links"
    __table_args__ = (Index("ix_category_link_pair", "business_id", "category_id", unique=True),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("business_categories.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
