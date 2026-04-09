"""add updated_at and version to context_tree_runs

Revision ID: f4452eb7a64f
Revises: b60ef06f1fcf
Create Date: 2026-04-09 18:05:44.890417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4452eb7a64f'
down_revision: Union[str, None] = 'b60ef06f1fcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('context_tree_runs', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('context_tree_runs', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('context_tree_runs', 'updated_at')
    op.drop_column('context_tree_runs', 'version')
