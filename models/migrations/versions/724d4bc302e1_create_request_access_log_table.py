"""create_request_access_log_table.

Revision ID: 724d4bc302e1
Revises: b2c47f915e6a
Create Date: 2026-09-18 00:00:00.000000

Adds an audit trail of PHI access (viewing a request's detail, or
downloading one of its generated documents) - distinct from
request_status_history, which only tracks status *changes*.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '724d4bc302e1'
down_revision: str | Sequence[str] | None = 'b2c47f915e6a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE phiaccessaction AS ENUM ("
        "'VIEW', 'DOWNLOAD_NOVITAS_PACKAGE', 'DOWNLOAD_CALL_SHEET', "
        "'DOWNLOAD_CMS1500'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )

    op.create_table(
        'request_access_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'request_id',
            sa.Integer(),
            nullable=False,
            comment='ID of the ambulance request that was accessed',
        ),
        sa.Column(
            'user_id',
            sa.Integer(),
            nullable=True,
            comment='ID of the user who accessed it, if known',
        ),
        sa.Column(
            'action',
            sa.Enum(
                'VIEW',
                'DOWNLOAD_NOVITAS_PACKAGE',
                'DOWNLOAD_CALL_SHEET',
                'DOWNLOAD_CMS1500',
                name='phiaccessaction',
                create_type=False,
            ),
            nullable=False,
            comment='What kind of PHI access this was',
        ),
        sa.ForeignKeyConstraint(
            ['request_id'], ['ambulance_requests.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_request_access_logs_request_id'),
        'request_access_logs',
        ['request_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_request_access_logs_request_id'),
        table_name='request_access_logs',
    )
    op.drop_table('request_access_logs')

    op.execute('DROP TYPE IF EXISTS phiaccessaction')
