"""create_incoming_faxes_table.

Revision ID: de37d6267b24
Revises: 4039f522c20f
Create Date: 2026-09-08 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'de37d6267b24'
down_revision: str | Sequence[str] | None = '4039f522c20f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE faxdirection AS ENUM ('INBOUND', 'OUTBOUND'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE faxstatus AS ENUM ("
        "'RECEIVED', 'PROCESSING', 'MATCHED', 'UNRESOLVED', 'FAILED'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )

    op.create_table(
        'incoming_faxes',
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
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='true',
        ),
        sa.Column(
            'deleted_at',
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment='Indicates if the instance is active',
        ),
        sa.Column(
            'direction',
            sa.Enum(
                'INBOUND', 'OUTBOUND', name='faxdirection', create_type=False
            ),
            nullable=False,
            server_default='INBOUND',
            comment='Fax direction (inbound/outbound)',
        ),
        sa.Column(
            'status',
            sa.Enum(
                'RECEIVED',
                'PROCESSING',
                'MATCHED',
                'UNRESOLVED',
                'FAILED',
                name='faxstatus',
                create_type=False,
            ),
            nullable=False,
            server_default='RECEIVED',
            comment='Current processing status of the fax',
        ),
        sa.Column(
            'provider_message_id',
            sa.String(length=100),
            nullable=False,
            comment=(
                "Fax provider's message ID, used to prevent duplicate "
                'processing of the same webhook event'
            ),
        ),
        sa.Column(
            'from_number',
            sa.String(length=50),
            nullable=True,
            comment='Sender fax number',
        ),
        sa.Column(
            'to_number',
            sa.String(length=50),
            nullable=True,
            comment='Recipient fax number',
        ),
        sa.Column(
            'page_count',
            sa.Integer(),
            nullable=True,
            comment='Number of pages in the fax',
        ),
        sa.Column(
            's3_key',
            sa.String(length=500),
            nullable=True,
            comment='S3 object key of the stored fax document',
        ),
        sa.Column(
            'content_type',
            sa.String(length=100),
            nullable=True,
            comment='MIME type of the stored document',
        ),
        sa.Column(
            'file_size',
            sa.Integer(),
            nullable=True,
            comment='Size of the stored document in bytes',
        ),
        sa.Column(
            'request_id',
            sa.Integer(),
            nullable=True,
            comment='Linked ambulance request, once matched',
        ),
        sa.Column(
            'matched_by_user_id',
            sa.Integer(),
            nullable=True,
            comment='User who manually linked this fax, if applicable',
        ),
        sa.ForeignKeyConstraint(
            ['request_id'], ['ambulance_requests.id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['matched_by_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_message_id'),
    )
    op.create_index(
        op.f('ix_incoming_faxes_request_id'),
        'incoming_faxes',
        ['request_id'],
    )
    op.create_index(
        op.f('ix_incoming_faxes_status'),
        'incoming_faxes',
        ['status'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_incoming_faxes_status'), table_name='incoming_faxes'
    )
    op.drop_index(
        op.f('ix_incoming_faxes_request_id'), table_name='incoming_faxes'
    )
    op.drop_table('incoming_faxes')

    op.execute('DROP TYPE IF EXISTS faxstatus')
    op.execute('DROP TYPE IF EXISTS faxdirection')
