"""add_request_file_uploaded_by_user_id.

Revision ID: c3d9e7f1a2b4
Revises: 724d4bc302e1
Create Date: 2026-10-19 00:00:00.000000

Adds the authorization boundary request_files was missing: there was no
column recording who uploaded a file, so any authenticated user could
pass another user's file ID into the extraction or submit flow and have
it linked into their own request (confirmed exploitable - see
services/ambulance_request.py for the fix). Already-linked files are
backfilled from their parent request's owner; pre-existing unlinked
("temporary") files have no recoverable owner and are left NULL, which
the application treats as owned by no one.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d9e7f1a2b4'
down_revision: str | Sequence[str] | None = '724d4bc302e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'request_files',
        sa.Column(
            'uploaded_by_user_id',
            sa.Integer(),
            nullable=True,
            comment=(
                'ID of the user who uploaded the file - the '
                'authorization boundary for linking an unattached '
                'file to a request; a NULL value (e.g. a pre-existing '
                'row from before this column existed) is never '
                'treated as owned by anyone'
            ),
        ),
    )
    op.create_foreign_key(
        'fk_request_files_uploaded_by_user_id_users',
        'request_files',
        'users',
        ['uploaded_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.execute(
        """
        UPDATE request_files
        SET uploaded_by_user_id = ambulance_requests.user_id
        FROM ambulance_requests
        WHERE request_files.request_id = ambulance_requests.id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_request_files_uploaded_by_user_id_users',
        'request_files',
        type_='foreignkey',
    )
    op.drop_column('request_files', 'uploaded_by_user_id')
