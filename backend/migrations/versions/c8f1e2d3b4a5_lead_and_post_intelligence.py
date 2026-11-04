"""lead and post intelligence extension

Extends social_content with fields for high-precision post intelligence:
author information, retrieval errors, extraction methods, matched queries,
run and duplicate references, classification scores, service tags,
and nullable engagement metrics.

Adds social_content_user_annotations to isolate user-owned CRM state,
hot lead flags, follow-up dates, customer need quotes, and personal notes
so automated pipeline re-runs never overwrite human annotations.

Revision ID: c8f1e2d3b4a5
Revises: c7d4e1a92b08
Create Date: 2026-11-05 00:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c8f1e2d3b4a5'
down_revision: Union[str, None] = 'c7d4e1a92b08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to social_content
    op.add_column('social_content', sa.Column('author_name', sa.String(255), nullable=True))
    op.add_column('social_content', sa.Column('author_username', sa.String(255), nullable=True))
    op.add_column('social_content', sa.Column('author_profile_url', sa.Text(), nullable=True))
    op.add_column('social_content', sa.Column('published_at_source', sa.String(100), nullable=True))
    op.add_column('social_content', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('social_content', sa.Column('retrieval_error', sa.Text(), nullable=True))
    op.add_column('social_content', sa.Column('extraction_method', sa.String(100), nullable=True))
    op.add_column('social_content', sa.Column('matched_query', sa.String(255), nullable=True))
    op.add_column('social_content', sa.Column('discovery_run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('social_content', sa.Column('duplicate_of_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('social_content', sa.Column('classification_score', sa.Integer(), nullable=True))
    op.add_column(
        'social_content',
        sa.Column('service_tags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False)
    )
    op.add_column('social_content', sa.Column('reactions_count', sa.Integer(), nullable=True))
    op.add_column('social_content', sa.Column('comments_count', sa.Integer(), nullable=True))
    op.add_column('social_content', sa.Column('reposts_count', sa.Integer(), nullable=True))
    op.add_column(
        'social_content',
        sa.Column('raw_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)
    )

    # 2. Add foreign keys for discovery_run_id and duplicate_of_id
    op.create_foreign_key(
        'fk_social_content_discovery_run_id',
        'social_content',
        'social_discovery_runs',
        ['discovery_run_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_social_content_duplicate_of_id',
        'social_content',
        'social_content',
        ['duplicate_of_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 3. Update check constraint on retrieval_status to allow required values
    op.drop_constraint('ck_social_content_retrieval_status', 'social_content', type_='check')
    op.create_check_constraint(
        'ck_social_content_retrieval_status',
        'social_content',
        "retrieval_status IN ("
        "'pending','full_text','snippet_only','blocked','failed','unsupported',"
        "'retrieved','indexed_snippet','public_page_retrieved','user_provided_url','inaccessible')"
    )

    # 4. Create social_content_user_annotations table
    op.create_table(
        'social_content_user_annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('content_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_status', sa.String(50), server_default=sa.text("'new'"), nullable=False),
        sa.Column('is_hot', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('follow_up_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_note', sa.Text(), nullable=True),
        sa.Column('quoted_customer_need', sa.Text(), nullable=True),
        sa.Column('services_to_sell', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('is_saved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['content_id'], ['social_content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('owner_user_id', 'content_id', name='uq_social_annotation_owner_content')
    )
    op.create_index('ix_social_annotation_owner_hot', 'social_content_user_annotations', ['owner_user_id', 'is_hot'])
    op.create_index('ix_social_annotation_owner_status', 'social_content_user_annotations', ['owner_user_id', 'lead_status'])
    op.create_index('ix_social_content_run_id', 'social_content', ['discovery_run_id'])
    op.create_index('ix_social_content_duplicate_of', 'social_content', ['duplicate_of_id'])


def downgrade() -> None:
    op.drop_table('social_content_user_annotations')
    op.drop_constraint('fk_social_content_duplicate_of_id', 'social_content', type_='foreignkey')
    op.drop_constraint('fk_social_content_discovery_run_id', 'social_content', type_='foreignkey')
    op.drop_constraint('ck_social_content_retrieval_status', 'social_content', type_='check')
    op.create_check_constraint(
        'ck_social_content_retrieval_status',
        'social_content',
        "retrieval_status IN ('retrieved','snippet_only','indexed_snippet',"
        "'public_page_retrieved','user_provided_url','inaccessible','unsupported')"
    )
    op.drop_column('social_content', 'raw_metadata')
    op.drop_column('social_content', 'reposts_count')
    op.drop_column('social_content', 'comments_count')
    op.drop_column('social_content', 'reactions_count')
    op.drop_column('social_content', 'service_tags')
    op.drop_column('social_content', 'classification_score')
    op.drop_column('social_content', 'duplicate_of_id')
    op.drop_column('social_content', 'discovery_run_id')
    op.drop_column('social_content', 'matched_query')
    op.drop_column('social_content', 'extraction_method')
    op.drop_column('social_content', 'retrieval_error')
    op.drop_column('social_content', 'last_seen_at')
    op.drop_column('social_content', 'published_at_source')
    op.drop_column('social_content', 'author_profile_url')
    op.drop_column('social_content', 'author_username')
    op.drop_column('social_content', 'author_name')

