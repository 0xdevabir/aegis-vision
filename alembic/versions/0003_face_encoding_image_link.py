"""link face encodings to their source photo

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('face_encodings', sa.Column('image_id', sa.Integer(), nullable=True))
    op.create_index('ix_face_encodings_image_id', 'face_encodings', ['image_id'])


def downgrade() -> None:
    op.drop_index('ix_face_encodings_image_id', table_name='face_encodings')
    op.drop_column('face_encodings', 'image_id')
