"""add_novitas_tracking_fields.

Revision ID: 8a1e7c3d9f42
Revises: de37d6267b24
Create Date: 2026-09-09 00:00:00.000000

Adds Novitas prior-authorization submission tracking to ambulance
requests, and extends the faxstatus enum with outbound-only values:
- utn
- novitas_status
- novitas_submitted_at
- novitas_fax_id
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8a1e7c3d9f42'
down_revision: str | Sequence[str] | None = 'de37d6267b24'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE faxstatus ADD VALUE IF NOT EXISTS 'QUEUED'")
    op.execute("ALTER TYPE faxstatus ADD VALUE IF NOT EXISTS 'SENT'")

    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE novitasstatus AS ENUM ("
        "'NOT_SUBMITTED', 'SUBMITTED', 'UTN_RECEIVED', "
        "'ADDITIONAL_INFO_REQUESTED', 'APPROVED', 'DENIED'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )

    op.add_column(
        'ambulance_requests',
        sa.Column(
            'utn',
            sa.String(length=50),
            nullable=True,
            comment=(
                'Unique Tracking Number issued by Novitas once a prior '
                'authorization decision is made (CMS-1500 Box 23)'
            ),
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'novitas_status',
            sa.Enum(
                'NOT_SUBMITTED',
                'SUBMITTED',
                'UTN_RECEIVED',
                'ADDITIONAL_INFO_REQUESTED',
                'APPROVED',
                'DENIED',
                name='novitasstatus',
                create_type=False,
            ),
            nullable=False,
            server_default='NOT_SUBMITTED',
            comment='Status of the external Novitas prior authorization',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'novitas_submitted_at',
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment='When the Novitas PA package was faxed to Novitas',
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'novitas_fax_id',
            sa.Integer(),
            nullable=True,
            comment=(
                'Outbound fax record for the Novitas PA package submission'
            ),
        ),
    )
    op.create_foreign_key(
        'fk_ambulance_requests_novitas_fax_id_incoming_faxes',
        'ambulance_requests',
        'incoming_faxes',
        ['novitas_fax_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_ambulance_requests_novitas_fax_id_incoming_faxes',
        'ambulance_requests',
        type_='foreignkey',
    )
    op.drop_column('ambulance_requests', 'novitas_fax_id')
    op.drop_column('ambulance_requests', 'novitas_submitted_at')
    op.drop_column('ambulance_requests', 'novitas_status')
    op.drop_column('ambulance_requests', 'utn')

    op.execute('DROP TYPE IF EXISTS novitasstatus')

    # faxstatus QUEUED/SENT values are not removed on downgrade: Postgres
    # does not support dropping individual enum values without the
    # rename-and-recreate dance, and no data uses them by this point.
