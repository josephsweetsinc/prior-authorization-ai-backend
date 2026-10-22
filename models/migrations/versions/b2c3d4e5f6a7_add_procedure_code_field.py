"""add_procedure_code_field.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-15 00:00:00.000000

Adds ambulance_requests.procedure_code - the HCPCS code (A0428 BLS or
A0426 ALS, the only two the real Novitas Form 13614 cover sheet
supports) - so it's editable on the request instead of hardcoded in the
PDF generator. Defaults existing rows to A0428, matching the generator's
prior hardcoded default.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE procedurecode AS ENUM ('A0428', 'A0426'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'procedure_code',
            sa.Enum(
                'A0428', 'A0426', name='procedurecode', create_type=False
            ),
            nullable=False,
            server_default='A0428',
            comment='HCPCS procedure code for the Novitas Form 13614 '
            'cover sheet (A0428 BLS or A0426 ALS, non-emergency)',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ambulance_requests', 'procedure_code')
    op.execute('DROP TYPE IF EXISTS procedurecode')
