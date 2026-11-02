"""Add the missing primary key to business_tags.

`0002` (a7189272189c) created this table with a UNIQUE constraint over
(business_id, tag_id) but **no primary key**, because the model declared both
over the identical column list and autogenerate emitted only one of them. The
following revision dropped the unique constraint, which left the table with no
primary key and no index enforcing uniqueness at all — duplicate tag links
became insertable.

This restores the key the model has always declared. It is a forward repair
rather than an edit to `0002`, because `0002` has already run against this
database; rewriting an applied migration is how a schema and its history stop
agreeing.

Lesson recorded in DECISIONS.md: when autogenerate creates a table whose primary
key and a unique constraint share the same columns, read the generated DDL.

Revision ID: 7c41d0b52ae3
Revises: 0e2cb7da9112
Create Date: 2026-11-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "7c41d0b52ae3"
down_revision: Union[str, None] = "0e2cb7da9112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_primary_key("business_tags_pkey", "business_tags", ["business_id", "tag_id"])


def downgrade() -> None:
    op.drop_constraint("business_tags_pkey", "business_tags", type_="primary")
