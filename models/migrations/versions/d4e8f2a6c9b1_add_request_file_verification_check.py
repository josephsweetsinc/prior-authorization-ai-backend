"""add_request_file_verification_check.

Revision ID: d4e8f2a6c9b1
Revises: 724d4bc302e1
Create Date: 2026-10-19 00:00:00.000000

Adds request_files.is_verification_of_medical_necessity, a cached
per-file AI content-check result. The check (does this file contain a
Verification of Medical Necessity document) is costly - it runs a
vision-model call per file - so caching it on the file row lets the
submission gate call it without re-running that check on every single
completion-status evaluation.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e8f2a6c9b1'
down_revision: str | Sequence[str] | None = '724d4bc302e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'request_files',
        sa.Column(
            'is_verification_of_medical_necessity',
            sa.Boolean(),
            nullable=True,
            comment=(
                'Whether this file is a Verification of Medical '
                'Necessity document, per a one-time AI content check. '
                'NULL means not yet checked - cached so the (costly, '
                'per-file) check runs once per file rather than on '
                'every completion-status check'
            ),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('request_files', 'is_verification_of_medical_necessity')
