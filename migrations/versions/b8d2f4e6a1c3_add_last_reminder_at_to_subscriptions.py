"""add last_reminder_at to subscriptions

Revision ID: b8d2f4e6a1c3
Revises: a7c9e2f3b1d4
Create Date: 2026-02-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d2f4e6a1c3'
down_revision = 'a7c9e2f3b1d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_reminder_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_column('last_reminder_at')
