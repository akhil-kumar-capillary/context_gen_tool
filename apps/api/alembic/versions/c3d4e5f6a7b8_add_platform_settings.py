"""add platform_settings table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('theme_preset', sa.String(length=50), nullable=True),
        sa.Column('primary_hsl_light', sa.String(length=50), nullable=True),
        sa.Column('primary_hsl_dark', sa.String(length=50), nullable=True),
        sa.Column('dark_mode_default', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Insert default row
    op.execute("""
        INSERT INTO platform_settings (id, theme_preset, primary_hsl_light, primary_hsl_dark, dark_mode_default)
        VALUES (1, 'slate_blue', '215 70% 55%', '215 70% 65%', false)
    """)


def downgrade() -> None:
    op.drop_table('platform_settings')
