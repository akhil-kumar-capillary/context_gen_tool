"""add content_versions table, migrate checkpoints, drop context_tree_checkpoints

Revision ID: a1b2c3d4e5f6
Revises: f4452eb7a64f
Create Date: 2026-04-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f4452eb7a64f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create content_versions table
    op.create_table(
        'content_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=255), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('previous_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('changed_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'entity_type', 'entity_id', 'version_number',
            name='uq_entity_version',
        ),
    )
    op.create_index(
        'ix_cv_entity_lookup',
        'content_versions',
        ['entity_type', 'entity_id', 'version_number'],
    )
    op.create_index('ix_cv_org', 'content_versions', ['org_id'])

    # 2. Migrate existing checkpoint data into content_versions.
    #    Each checkpoint becomes a version record for its parent run.
    #    We use ROW_NUMBER() to assign sequential version numbers per run,
    #    ordered by created_at.
    op.execute("""
        INSERT INTO content_versions (
            id, entity_type, entity_id, version_number,
            snapshot, previous_snapshot,
            change_type, change_summary, changed_fields,
            changed_by_user_id, org_id, created_at
        )
        SELECT
            cp.id,
            'context_tree',
            cp.run_id::text,
            ROW_NUMBER() OVER (PARTITION BY cp.run_id ORDER BY cp.created_at),
            cp.tree_data,
            NULL,
            'update',
            COALESCE(cp.change_summary, cp.label, 'Migrated from checkpoint'),
            '["tree_data"]'::jsonb,
            cp.user_id,
            cp.org_id,
            cp.created_at
        FROM context_tree_checkpoints cp
    """)

    # 3. Drop old checkpoints table
    op.drop_index(
        op.f('ix_context_tree_checkpoints_run_id'),
        table_name='context_tree_checkpoints',
    )
    op.drop_index(
        op.f('ix_context_tree_checkpoints_org_id'),
        table_name='context_tree_checkpoints',
    )
    op.drop_table('context_tree_checkpoints')


def downgrade() -> None:
    # WARNING: This downgrade is DESTRUCTIVE. All content_versions data
    # (version history) will be lost and cannot be migrated back to
    # context_tree_checkpoints due to schema differences.
    # Only run this in development/testing.

    # Recreate checkpoints table
    op.create_table(
        'context_tree_checkpoints',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('tree_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('node_count', sa.Integer(), nullable=True),
        sa.Column('leaf_count', sa.Integer(), nullable=True),
        sa.Column('health_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['context_tree_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_context_tree_checkpoints_org_id'),
        'context_tree_checkpoints',
        ['org_id'],
    )
    op.create_index(
        op.f('ix_context_tree_checkpoints_run_id'),
        'context_tree_checkpoints',
        ['run_id'],
    )

    # Drop content_versions
    op.drop_index('ix_cv_org', table_name='content_versions')
    op.drop_index('ix_cv_entity_lookup', table_name='content_versions')
    op.drop_table('content_versions')
