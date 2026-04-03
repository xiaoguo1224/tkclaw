"""merge workspace task archive head

Revision ID: 4d2b9a8e1f77
Revises: bbd8065a731d, c3d8f952a6ea
Create Date: 2026-04-03 16:45:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "4d2b9a8e1f77"
down_revision: Union[str, Sequence[str], None] = ("bbd8065a731d", "c3d8f952a6ea")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
