"""merge_heads_after_pr97_98_99

Revision ID: 50a50b18ebb5
Revises: b2c3d4e5f6a7, dda605b1d03f
Create Date: 2026-10-22 23:07:27.958294

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50a50b18ebb5'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6a7', 'dda605b1d03f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
