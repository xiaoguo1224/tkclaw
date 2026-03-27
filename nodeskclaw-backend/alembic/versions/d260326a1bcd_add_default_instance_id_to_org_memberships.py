"""add default instance id to org memberships

Revision ID: d260326a1bcd
Revises: a1b2c3d4e5f6
Create Date: 2026-03-26 11:35:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d260326a1bcd"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_memberships",
        sa.Column("default_instance_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_memberships_default_instance_id",
        "org_memberships",
        "instances",
        ["default_instance_id"],
        ["id"],
    )
    op.create_index(
        "ix_org_memberships_default_instance_id",
        "org_memberships",
        ["default_instance_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_org_memberships_default_instance_id", table_name="org_memberships")
    op.drop_constraint("fk_org_memberships_default_instance_id", "org_memberships", type_="foreignkey")
    op.drop_column("org_memberships", "default_instance_id")
