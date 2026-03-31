"""合并多 head 迁移链

Revision ID: bbd8065a731d
Revises: 68c9c4eb557f, f7d91b2c4a5e
Create Date: 2026-03-31 13:27:00.504780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbd8065a731d'
down_revision: Union[str, Sequence[str], None] = ('68c9c4eb557f', 'f7d91b2c4a5e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
