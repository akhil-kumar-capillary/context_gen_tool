"""add composite index on content_versions for common query pattern

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index matching the primary query pattern:
    # WHERE entity_type = ? AND entity_id = ? AND org_id = ?
    # ORDER BY version_number DESC
    op.create_index(
        'ix_cv_full_lookup',
        'content_versions',
        ['entity_type', 'entity_id', 'org_id', 'version_number'],
    )


def downgrade() -> None:
    op.drop_index('ix_cv_full_lookup', table_name='content_versions')
