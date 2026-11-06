"""add local scan runs and units

Revision ID: d4a8e2b9c710
Revises: f1a7c9d2e3b4
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4a8e2b9c710"
down_revision: Union[str, None] = "f1a7c9d2e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_scan_runs",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("niche", sa.String(length=160), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=False),
        sa.Column("country", sa.String(length=100), server_default=sa.text("'India'"), nullable=False),
        sa.Column(
            "query_variants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "locality_units",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.String(length=100),
            server_default=sa.text("'planning'"),
            nullable=False,
        ),
        sa.Column(
            "progress_percent",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column("retries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "source_coverage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'planning', 'running', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_local_scan_run_status",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_local_scan_run_progress",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_local_scan_runs_owner_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_local_scan_runs_owner_status",
        "local_scan_runs",
        ["owner_user_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_local_scan_runs_owner_user_id",
        "local_scan_runs",
        ["owner_user_id"],
        unique=False,
    )

    op.create_table(
        "local_scan_units",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scan_run_id", sa.UUID(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("unit_kind", sa.String(length=50), nullable=False),
        sa.Column("query_or_url", sa.Text(), nullable=False),
        sa.Column("locality", sa.String(length=150), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("candidates_found", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidates_accepted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidates_duplicate", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "execution_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_local_scan_unit_status",
        ),
        sa.ForeignKeyConstraint(
            ["scan_run_id"],
            ["local_scan_runs.id"],
            name="fk_local_scan_units_scan_run_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_local_scan_units_run_status",
        "local_scan_units",
        ["scan_run_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_local_scan_units_source",
        "local_scan_units",
        ["source_name", "status"],
        unique=False,
    )
    op.create_index(
        "ix_local_scan_units_scan_run_id",
        "local_scan_units",
        ["scan_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("local_scan_units")
    op.drop_table("local_scan_runs")

