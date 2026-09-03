"""password reset codes

Revision ID: c41f7a90d2e1
Revises: b93084332416
Create Date: 2026-09-02 23:20:00.000000+00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'c41f7a90d2e1'
down_revision: str | None = 'b93084332416'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'password_reset_codes',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('user_id', sa.String(length=26), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_password_reset_codes_user_id', 'password_reset_codes', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_password_reset_codes_user_id', table_name='password_reset_codes')
    op.drop_table('password_reset_codes')
