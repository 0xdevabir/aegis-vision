"""camera heading / field of view / range for the map

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('heading', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('fov', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('range_m', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('cameras', 'range_m')
    op.drop_column('cameras', 'fov')
    op.drop_column('cameras', 'heading')
