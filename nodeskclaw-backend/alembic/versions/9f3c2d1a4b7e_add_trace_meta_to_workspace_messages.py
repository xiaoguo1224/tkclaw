"""add trace meta to workspace messages

Revision ID: 9f3c2d1a4b7e
Revises: 4d2b9a8e1f77
Create Date: 2026-04-07 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9f3c2d1a4b7e"
down_revision: Union[str, Sequence[str], None] = "4d2b9a8e1f77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_messages",
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_messages", "meta")
