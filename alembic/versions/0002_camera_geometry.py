"""camera zone/line geometry

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('geometry', sa.Text(), nullable=True))
    op.add_column('cameras', sa.Column('geometry_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('cameras', 'geometry_updated_at')
    op.drop_column('cameras', 'geometry')
