"""add isolated verified prospecting tables

Revision ID: f1a7c9d2e3b4
Revises: c8f1e2d3b4a5
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a7c9d2e3b4"
down_revision: Union[str, None] = "c8f1e2d3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verified_prospecting_runs",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("niche", sa.String(length=160), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=False),
        sa.Column(
            "source_kind",
            sa.String(length=30),
            server_default=sa.text("'web_index'"),
            nullable=False,
        ),
        sa.Column("max_candidates", sa.Integer(), server_default=sa.text("25"), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column(
            "stage", sa.String(length=160), server_default=sa.text("'Queued'"), nullable=False
        ),
        sa.Column("progress_percent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("saved_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cancellation_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
            "status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')",
            name="ck_verified_prospecting_run_status",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_verified_prospecting_run_progress",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verified_prospecting_runs_owner_user_id"),
        "verified_prospecting_runs",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verified_prospecting_runs_status"),
        "verified_prospecting_runs",
        ["status"],
        unique=False,
    )
    op.create_table(
        "verified_prospecting_leads",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column(
            "website_status",
            sa.String(length=20),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column("public_phone", sa.String(length=80), nullable=True),
        sa.Column("public_email", sa.String(length=320), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("potential_score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "score_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
            "website_status IN ('has_website', 'unknown')",
            name="ck_verified_prospecting_lead_website_status",
        ),
        sa.CheckConstraint(
            "potential_score >= 0 AND potential_score <= 100",
            name="ck_verified_prospecting_lead_score",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["verified_prospecting_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "source_url", name="uq_verified_prospecting_lead_run_source"),
    )
    op.create_index(
        op.f("ix_verified_prospecting_leads_run_id"),
        "verified_prospecting_leads",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_verified_prospecting_leads_run_id"), table_name="verified_prospecting_leads"
    )
    op.drop_table("verified_prospecting_leads")
    op.drop_index(
        op.f("ix_verified_prospecting_runs_status"), table_name="verified_prospecting_runs"
    )
    op.drop_index(
        op.f("ix_verified_prospecting_runs_owner_user_id"), table_name="verified_prospecting_runs"
    )
    op.drop_table("verified_prospecting_runs")
