"""ops: audit log, retention policy, attachment scan status, FTS index

Revision ID: a11ce0000001
Revises: d52e8b13f7a2
Create Date: 2026-09-03 03:00:00.000000+00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'a11ce0000001'
down_revision: str | None = 'd52e8b13f7a2'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('workspace_id', sa.String(length=26), nullable=True),
        sa.Column('actor_id', sa.String(length=26), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=26), nullable=True),
        sa.Column('target_label', sa.String(length=200), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'],
                                name='fk_audit_events_workspace_id_workspaces',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'],
                                name='fk_audit_events_actor_id_users', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name='pk_audit_events'),
    )
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_workspace_id_id', 'audit_events', ['workspace_id', 'id'])
    op.create_index('ix_audit_events_actor_id_id', 'audit_events', ['actor_id', 'id'])

    with op.batch_alter_table('workspaces') as batch:
        batch.add_column(sa.Column('retention_days_messages', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('retention_days_files', sa.Integer(), nullable=True))
    with op.batch_alter_table('channels') as batch:
        batch.add_column(sa.Column('retention_days', sa.Integer(), nullable=True))
    with op.batch_alter_table('files') as batch:
        batch.add_column(
            sa.Column('scan_status', sa.String(length=16), nullable=False,
                      server_default='skipped')
        )

    # Full-text search index — Postgres only. SQLite keeps the LIKE scan.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_messages_body_fts ON messages "
            "USING GIN (to_tsvector('simple', body))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_messages_body_fts')
    with op.batch_alter_table('files') as batch:
        batch.drop_column('scan_status')
    with op.batch_alter_table('channels') as batch:
        batch.drop_column('retention_days')
    with op.batch_alter_table('workspaces') as batch:
        batch.drop_column('retention_days_files')
        batch.drop_column('retention_days_messages')
    op.drop_index('ix_audit_events_actor_id_id', table_name='audit_events')
    op.drop_index('ix_audit_events_workspace_id_id', table_name='audit_events')
    op.drop_index('ix_audit_events_action', table_name='audit_events')
    op.drop_table('audit_events')
