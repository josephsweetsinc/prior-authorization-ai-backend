"""merge_heads_for_integration_test

Revision ID: a3775870367b
Revises: b2c3d4e5f6a7, c3d9e7f1a2b4, d4e8f2a6c9b1
Create Date: 2026-10-22 21:05:34.160716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3775870367b'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6a7', 'c3d9e7f1a2b4', 'd4e8f2a6c9b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
