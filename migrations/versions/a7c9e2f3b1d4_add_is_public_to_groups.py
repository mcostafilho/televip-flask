"""add is_public to groups

Revision ID: a7c9e2f3b1d4
Revises: 829384b34aa8
Create Date: 2026-02-12 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c9e2f3b1d4'
down_revision = '829384b34aa8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_public', sa.Boolean(), nullable=True, server_default=sa.text('false')))


def downgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_column('is_public')
