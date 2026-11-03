"""owner_user_id references users(id)

Every owned table already carried `owner_user_id` and `database-schema.md` §4.3
documented it as `REFERENCES users(id)`, but the database never enforced it: a
row could outlive the account that created it and nothing would object. The
development database had accumulated 450 such rows.

The constraints are added `NOT VALID` on purpose. Validating them would require
either deleting rows that already exist or refusing to migrate, and neither is
acceptable in a migration that must not touch existing data. `NOT VALID` still
enforces the rule on every new and updated row, so the hole closes going forward
while the legacy rows stay visible to the integrity audit until they are
explicitly repaired.

Revision ID: c7d4e1a92b08
Revises: ba881785925a
Create Date: 2026-11-03 18:05:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = 'c7d4e1a92b08'
down_revision: Union[str, None] = 'ba881785925a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OWNED_TABLES: tuple[str, ...] = (
    'audit_logs',
    'business_notes',
    'business_opportunities',
    'businesses',
    'campaigns',
    'crm_activities',
    'crm_business_records',
    'crm_pipelines',
    'discovery_jobs',
    'email_accounts',
    'email_messages',
    'export_jobs',
    'import_jobs',
    'notifications',
    'retention_policies',
    'saved_reports',
    'schedules',
    'search_areas',
    'search_presets',
    'searches',
    'services',
    'social_content',
    'social_discovery_runs',
    'social_profiles',
    'social_research_queries',
    'social_saved_items',
    'social_search_tracks',
    'source_configurations',
    'source_records',
    'startup_watchlists',
    'startups',
    'suppression_list',
    'tags',
    'workflow_executions',
    'workflows',
)


def upgrade() -> None:
    for table in _OWNED_TABLES:
        op.create_foreign_key(
            f'fk_{table}_owner_user_id_users',
            table,
            'users',
            ['owner_user_id'],
            ['id'],
            postgresql_not_valid=True,
        )


def downgrade() -> None:
    for table in _OWNED_TABLES:
        op.drop_constraint(
            f'fk_{table}_owner_user_id_users', table, type_='foreignkey'
        )
