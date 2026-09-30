"""add_call_sheet_data_field.

Revision ID: b2c47f915e6a
Revises: 8a1e7c3d9f42
Create Date: 2026-09-09 00:00:00.000000

Adds a JSONB column storing the interactively-filled values for the
Masters Ambulance Call Sheet's ~120 AcroForm fields, keyed by the
template's own field names.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c47f915e6a'
down_revision: str | Sequence[str] | None = '8a1e7c3d9f42'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ambulance_requests',
        sa.Column(
            'call_sheet_data',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                'Values for the Masters Ambulance Call Sheet AcroForm '
                'fields, keyed by the template field name (e.g. '
                '"Dispatched", "Chief ComplaintsRow1"), filled in '
                'interactively before the PDF is generated'
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ambulance_requests', 'call_sheet_data')
