"""Install PostgreSQL extensions required by the schema.

Kept as its own revision because Alembic autogenerate does not emit extension
DDL, and the initial schema revision depends on both of these existing first:

- ``pgcrypto`` provides ``gen_random_uuid()``, the server-side UUID default.
- ``pg_trgm`` provides trigram indexes used for fuzzy name and address matching.

Revision ID: 0001_extensions
Revises:
Create Date: 2026-11-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001_extensions"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Dropped in reverse order; both are owned by this revision alone.
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
