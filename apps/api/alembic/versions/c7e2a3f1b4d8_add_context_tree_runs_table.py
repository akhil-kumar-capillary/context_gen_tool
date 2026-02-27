"""add context_tree_runs table

Revision ID: c7e2a3f1b4d8
Revises: b3f8a1c9e2d7
Create Date: 2026-02-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7e2a3f1b4d8'
down_revision: Union[str, None] = 'b3f8a1c9e2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('context_tree_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('input_sources', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('input_context_count', sa.Integer(), nullable=True),
        sa.Column('tree_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('token_usage', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('system_prompt_used', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_context_tree_runs_org_id'), 'context_tree_runs', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_context_tree_runs_org_id'), table_name='context_tree_runs')
    op.drop_table('context_tree_runs')
