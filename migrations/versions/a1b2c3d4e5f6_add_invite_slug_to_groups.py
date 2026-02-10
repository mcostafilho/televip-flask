"""add invite_slug to groups

Revision ID: a1b2c3d4e5f6
Revises: b3b245cfce4e
Create Date: 2026-02-10 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import secrets


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'b3b245cfce4e'
branch_labels = None
depends_on = None


def upgrade():
    # Add column as nullable first
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invite_slug', sa.String(length=16), nullable=True))

    # Generate slugs for existing groups
    conn = op.get_bind()
    groups = conn.execute(sa.text('SELECT id FROM groups')).fetchall()
    for group in groups:
        slug = secrets.token_urlsafe(6)
        conn.execute(
            sa.text('UPDATE groups SET invite_slug = :slug WHERE id = :id'),
            {'slug': slug, 'id': group[0]}
        )

    # Now make it non-nullable and add unique constraint
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.alter_column('invite_slug', nullable=False)
        batch_op.create_unique_constraint('uq_groups_invite_slug', ['invite_slug'])


def downgrade():
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_constraint('uq_groups_invite_slug', type_='unique')
        batch_op.drop_column('invite_slug')
