"""app platform: command/interaction/home URLs, signing secret, review, webhook deliveries

Revision ID: c33ce0000003
Revises: b22ce0000002
Create Date: 2026-09-03 05:00:00.000000+00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'c33ce0000003'
down_revision: str | None = 'b22ce0000002'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('apps') as batch:
        batch.add_column(sa.Column('command_url', sa.Text(), nullable=True))
        batch.add_column(sa.Column('interaction_url', sa.Text(), nullable=True))
        batch.add_column(sa.Column('home_url', sa.Text(), nullable=True))
        batch.add_column(sa.Column('app_secret', sa.Text(), nullable=True))
        batch.add_column(sa.Column('review_note', sa.String(length=500), nullable=True))

    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('app_id', sa.String(length=26), nullable=False),
        sa.Column('installation_id', sa.String(length=26), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='event'),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_status_code', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('channel_id', sa.String(length=26), nullable=True),
        sa.Column('response_nonce', sa.String(length=64), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['apps.id'],
                                name='fk_webhook_deliveries_app_id_apps', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['installation_id'], ['app_installations.id'],
            name='fk_webhook_deliveries_installation_id_app_installations', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_webhook_deliveries'),
    )
    op.create_index('ix_webhook_deliveries_app_id_id', 'webhook_deliveries', ['app_id', 'id'])
    op.create_index('ix_webhook_deliveries_status_next', 'webhook_deliveries',
                    ['status', 'next_attempt_at'])
    op.create_index('ix_webhook_deliveries_nonce', 'webhook_deliveries', ['response_nonce'],
                    unique=True)


def downgrade() -> None:
    op.drop_index('ix_webhook_deliveries_nonce', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_status_next', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_app_id_id', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')
    with op.batch_alter_table('apps') as batch:
        batch.drop_column('review_note')
        batch.drop_column('app_secret')
        batch.drop_column('home_url')
        batch.drop_column('interaction_url')
        batch.drop_column('command_url')
