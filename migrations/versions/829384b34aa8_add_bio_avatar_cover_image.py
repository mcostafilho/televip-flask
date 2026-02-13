"""add bio, avatar_url to Creator and cover_image_url to Group

Revision ID: 829384b34aa8
Revises: ff3a3fbb473f
Create Date: 2026-02-12 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '829384b34aa8'
down_revision = 'ff3a3fbb473f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('creators', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bio', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('avatar_url', sa.String(length=500), nullable=True))

    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cover_image_url', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_column('cover_image_url')

    with op.batch_alter_table('creators', schema=None) as batch_op:
        batch_op.drop_column('avatar_url')
        batch_op.drop_column('bio')
