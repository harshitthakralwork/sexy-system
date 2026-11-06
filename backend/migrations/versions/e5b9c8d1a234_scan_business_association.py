"""add local scan businesses association table

Revision ID: e5b9c8d1a234
Revises: d4a8e2b9c710
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b9c8d1a234"
down_revision: Union[str, None] = "d4a8e2b9c710"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_scan_businesses",
        sa.Column("scan_run_id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name="fk_local_scan_businesses_business_id_businesses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_run_id"],
            ["local_scan_runs.id"],
            name="fk_local_scan_businesses_scan_run_id_local_scan_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scan_run_id", "business_id", name="pk_local_scan_businesses"),
    )
    op.create_index(
        "ix_local_scan_businesses_biz",
        "local_scan_businesses",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        "ix_local_scan_businesses_run",
        "local_scan_businesses",
        ["scan_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_local_scan_businesses_run", table_name="local_scan_businesses")
    op.drop_index("ix_local_scan_businesses_biz", table_name="local_scan_businesses")
    op.drop_table("local_scan_businesses")

