"""usability: do-not-disturb, saved items + reminders, link previews, @here

Revision ID: b22ce0000002
Revises: a11ce0000001
Create Date: 2026-09-03 04:00:00.000000+00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'b22ce0000002'
down_revision: str | None = 'a11ce0000001'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('dnd_start', sa.String(length=5), nullable=True))
        batch.add_column(sa.Column('dnd_end', sa.String(length=5), nullable=True))
        batch.add_column(
            sa.Column('dnd_days', sa.JSON(), nullable=False, server_default='[0, 1, 2, 3, 4]')
        )
        batch.add_column(
            sa.Column('notify_paused_until', sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('broadcast', sa.String(length=8), nullable=True))

    op.create_table(
        'saved_items',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('user_id', sa.String(length=26), nullable=False),
        sa.Column('message_id', sa.String(length=26), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_saved_items_user_id_users', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'],
                                name='fk_saved_items_message_id_messages', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_saved_items'),
        sa.UniqueConstraint('user_id', 'message_id', name='uq_saved_items_user_id_message_id'),
    )
    op.create_index('ix_saved_items_user_id_done_at_id', 'saved_items',
                    ['user_id', 'done_at', 'id'])
    op.create_index('ix_saved_items_remind_at', 'saved_items', ['remind_at'])

    op.create_table(
        'link_previews',
        sa.Column('url_hash', sa.String(length=64), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=True),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('site_name', sa.String(length=200), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('url_hash', name='pk_link_previews'),
    )


def downgrade() -> None:
    op.drop_table('link_previews')
    op.drop_index('ix_saved_items_remind_at', table_name='saved_items')
    op.drop_index('ix_saved_items_user_id_done_at_id', table_name='saved_items')
    op.drop_table('saved_items')
    with op.batch_alter_table('messages') as batch:
        batch.drop_column('broadcast')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('notify_paused_until')
        batch.drop_column('dnd_days')
        batch.drop_column('dnd_end')
        batch.drop_column('dnd_start')
