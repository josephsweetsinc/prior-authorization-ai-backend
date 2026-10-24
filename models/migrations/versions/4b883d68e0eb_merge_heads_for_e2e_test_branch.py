"""merge_heads_for_e2e_test_branch

Revision ID: 4b883d68e0eb
Revises: 50a50b18ebb5, a3775870367b
Create Date: 2026-10-24 03:30:42.596009

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b883d68e0eb'
down_revision: Union[str, Sequence[str], None] = ('50a50b18ebb5', 'a3775870367b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
