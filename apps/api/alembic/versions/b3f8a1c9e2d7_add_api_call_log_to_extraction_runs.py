"""add api_call_log to config_extraction_runs

Revision ID: b3f8a1c9e2d7
Revises: ae4fe11527fd
Create Date: 2026-02-25 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3f8a1c9e2d7'
down_revision: Union[str, None] = 'ae4fe11527fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'config_extraction_runs',
        sa.Column('api_call_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('config_extraction_runs', 'api_call_log')
