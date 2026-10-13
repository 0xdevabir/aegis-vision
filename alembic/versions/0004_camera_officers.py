"""police officer <-> camera assignment, officer phone

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(30), nullable=True))
    op.create_table(
        'camera_officers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('camera_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('camera_id', 'user_id', name='uq_camera_officer'),
    )
    op.create_index('ix_camera_officers_camera_id', 'camera_officers', ['camera_id'])
    op.create_index('ix_camera_officers_user_id', 'camera_officers', ['user_id'])


def downgrade() -> None:
    op.drop_table('camera_officers')
    op.drop_column('users', 'phone')
