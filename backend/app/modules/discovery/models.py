from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

JOB_STATUSES = ("queued", "running", "completed", "failed", "paused", "cancelled", "blocked")
EXECUTION_TARGETS = ("cloud_preferred", "local_preferred", "either", "local_only")


class SearchPreset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "search_presets"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_search_presets_owner_user_id_users"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    keywords: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    location_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_ids: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    filters: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class Search(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "searches"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_searches_owner_user_id_users"),
        nullable=False, index=True,
    )
    preset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("search_presets.id", ondelete="SET NULL"), nullable=True
    )
    area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("search_areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    execution_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", server_default=text("'queued'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SearchArea(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A geographic scope a user drew, resolved or saved.

    The geometry lives here once, not in every search that used it: a saved area
    that is corrected must not leave stale shapes behind in past searches, and a
    re-run has to ask about the same ground it was saved with.
    """

    __tablename__ = "search_areas"
    __table_args__ = (
        CheckConstraint(
            "shape_type IN ('circle', 'rectangle', 'polygon', 'administrative')",
            name="ck_search_area_shape",
        ),
        CheckConstraint(
            "radius_m IS NULL OR (radius_m > 0 AND radius_m <= 50000)", name="ck_search_area_radius"
        ),
        CheckConstraint(
            "bbox_west <= bbox_east AND bbox_south <= bbox_north",
            name="ck_search_area_bbox_ordered",
        ),
        CheckConstraint(
            "bbox_south >= -90 AND bbox_north <= 90 AND bbox_west >= -180 AND bbox_east <= 180",
            name="ck_search_area_bbox_ranges",
        ),
        CheckConstraint("area_km2 >= 0", name="ck_search_area_size_nonnegative"),
        CheckConstraint(
            "shape_type <> 'circle' OR (center_latitude IS NOT NULL AND radius_m IS NOT NULL)",
            name="ck_search_area_circle_complete",
        ),
        CheckConstraint(
            "shape_type <> 'polygon' OR polygon IS NOT NULL", name="ck_search_area_polygon_present"
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_search_areas_owner_user_id_users"),
        nullable=False, index=True,
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True, default="leads")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    shape_type: Mapped[str] = mapped_column(String(20), nullable=False)
    center_latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    center_longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    radius_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_west: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    bbox_south: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    bbox_east: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    bbox_north: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    polygon: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    area_km2: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    admin_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    admin_locality: Mapped[str | None] = mapped_column(String(150), nullable=True)
    categories: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    geocode: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveryJob(Base, UUIDPrimaryKeyMixin):
    """A background unit of work with real, observed progress.

    ``progress_percent`` is written from processed-record counts, never
    estimated, and ``blocked`` is a reportable state for a job waiting on a
    worker that is not currently available.
    """

    __tablename__ = "discovery_jobs"
    __table_args__ = (
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="ck_job_progress_range"
        ),
        CheckConstraint("processed_records >= 0", name="ck_job_processed_nonnegative"),
        CheckConstraint("failed_records >= 0", name="ck_job_failed_nonnegative"),
        CheckConstraint("total_records >= 0", name="ck_job_total_nonnegative"),
    )

    search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("searches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_discovery_jobs_owner_user_id_users"),
        nullable=False, index=True,
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    execution_target: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="local_preferred",
        server_default=text("'local_preferred'"),
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    progress_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default=text("0")
    )
    total_records: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    processed_records: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failed_records: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(155), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class JobBatch(Base, UUIDPrimaryKeyMixin):
    """One unit of work inside a job: a tile against a source, or one whole query.

    For geographic jobs this row *is* the tile's state, which is what lets a
    region show which parts answered, which were cut off, and which can be
    re-run alone without asking the provider about ground it already covered.
    """

    __tablename__ = "job_batches"
    __table_args__ = (
        CheckConstraint("records_expected >= 0", name="ck_batch_expected_nonnegative"),
        CheckConstraint("records_processed >= 0", name="ck_batch_processed_nonnegative"),
        CheckConstraint(
            "unit_kind IN ('tile', 'single_query', 'keyword', 'source_probe')",
            name="ck_batch_unit_kind",
        ),
        # A tile is asked once per source per job. Without this, a retry that lost
        # its response could double-count the same ground as new work.
        UniqueConstraint("job_id", "tile_key", "source_id", name="uq_batch_job_tile_source"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="single_query", server_default=text("'single_query'")
    )
    # Deterministic identity for a tile: the same area and tile size always produce
    # the same key, which is what makes a re-run able to say "already done".
    tile_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bounds: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    records_expected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("discovery_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class SourceRecord(Base):
    """Raw payload as returned by a source, before normalisation.

    Kept separate from normalised entities so filtering and scoring never
    destroy what was actually collected, and so retention can expire the raw
    copy while the promoted business record survives.
    """

    __tablename__ = "source_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("discovery_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Which unit of work produced this record. Nullable: imports and non-tiled jobs
    # have no tile, and provenance that cannot be named is recorded as unknown
    # rather than guessed.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("job_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_source_records_owner_user_id_users"),
        nullable=False, index=True,
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'"), index=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SourceRecordLink(Base):
    """Links a raw record to the entity it produced.

    ``entity_type`` is a validated registry value, not a free-form string,
    because a polymorphic UUID cannot be protected by a database foreign key.
    """

    __tablename__ = "source_record_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("source_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
