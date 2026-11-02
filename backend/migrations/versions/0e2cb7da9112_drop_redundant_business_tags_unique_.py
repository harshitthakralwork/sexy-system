"""Drop the redundant unique constraint on business_tags.

The composite primary key on (business_id, tag_id) already enforces exactly this
uniqueness. The extra unique constraint made PostgreSQL maintain a second index
over the same two columns for no benefit.

It is removed here rather than left alone because Alembic's autogenerate does not
report it in either direction: the model no longer declares it, the database still
has it, and nothing would ever notice. A schema that silently diverges from the
models is how a later migration ends up surprised.

Revision ID: 0e2cb7da9112
Revises: a7189272189c
Create Date: 2026-11-02
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0e2cb7da9112"
down_revision: Union[str, None] = "a7189272189c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_business_tag", "business_tags", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_business_tag", "business_tags", ["business_id", "tag_id"])
