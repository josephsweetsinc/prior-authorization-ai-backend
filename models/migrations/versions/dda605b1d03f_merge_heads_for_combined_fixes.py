"""merge_heads_for_combined_fixes

Revision ID: dda605b1d03f
Revises: c3d9e7f1a2b4, d4e8f2a6c9b1
Create Date: 2026-10-22 22:57:54.681305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dda605b1d03f'
down_revision: Union[str, Sequence[str], None] = ('c3d9e7f1a2b4', 'd4e8f2a6c9b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
