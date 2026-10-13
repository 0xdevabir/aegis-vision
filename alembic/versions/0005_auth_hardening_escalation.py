"""login lockout columns and alert escalation timestamp

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('alerts', sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('alerts', 'escalated_at')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_attempts')
