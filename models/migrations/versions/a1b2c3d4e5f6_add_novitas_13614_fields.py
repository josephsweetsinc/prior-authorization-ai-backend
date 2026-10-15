"""add_novitas_13614_fields.

Revision ID: a1b2c3d4e5f6
Revises: 724d4bc302e1
Create Date: 2026-10-15 00:00:00.000000

Adds the fields needed to fill the real Novitas Form 13614 cover sheet:
- ambulance_requests.number_of_trips / authorization_start_date, which a
  physician's order for repetitive non-emergent transport may specify.
- organizations.npi / address / phone / fax, the ambulance provider's own
  billing identity (set once per organization, not per request).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '724d4bc302e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'number_of_trips',
            sa.Integer(),
            nullable=True,
            comment=(
                'Number of trips requested under this repetitive '
                'authorization (Novitas Form 13614), not to exceed 80 '
                'in 60 days'
            ),
        ),
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'authorization_start_date',
            sa.Date(),
            nullable=True,
            comment='Start date of the requested authorization period '
            '(Novitas Form 13614)',
        ),
    )
    op.add_column(
        'organizations',
        sa.Column(
            'npi',
            sa.String(length=10),
            nullable=True,
            comment=(
                "Organization's own National Provider Identifier, as the "
                'rendering (ambulance) provider on Novitas Form 13614 - '
                "distinct from a request's ordering_physician_npi"
            ),
        ),
    )
    op.add_column(
        'organizations',
        sa.Column(
            'address',
            sa.String(length=500),
            nullable=True,
            comment="Organization's billing name and address, as printed "
            'on Novitas Form 13614',
        ),
    )
    op.add_column(
        'organizations',
        sa.Column(
            'phone',
            sa.String(length=50),
            nullable=True,
            comment='Contact phone number for Novitas Form 13614',
        ),
    )
    op.add_column(
        'organizations',
        sa.Column(
            'fax',
            sa.String(length=50),
            nullable=True,
            comment='Contact fax number for Novitas Form 13614',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'fax')
    op.drop_column('organizations', 'phone')
    op.drop_column('organizations', 'address')
    op.drop_column('organizations', 'npi')
    op.drop_column('ambulance_requests', 'authorization_start_date')
    op.drop_column('ambulance_requests', 'number_of_trips')
