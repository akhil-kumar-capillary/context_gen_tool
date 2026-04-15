"""add source_type and source_table_name to analysis_runs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make run_id nullable (table-mode analysis has no extraction run)
    op.alter_column('analysis_runs', 'run_id', nullable=True)

    # Add source tracking columns
    op.add_column('analysis_runs',
        sa.Column('source_type', sa.String(length=20), nullable=False, server_default='extraction'))
    op.add_column('analysis_runs',
        sa.Column('source_table_name', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_runs', 'source_table_name')
    op.drop_column('analysis_runs', 'source_type')
    op.alter_column('analysis_runs', 'run_id', nullable=False)
