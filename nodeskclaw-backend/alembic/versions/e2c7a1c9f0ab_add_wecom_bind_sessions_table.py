"""add wecom bind sessions table

Revision ID: e2c7a1c9f0ab
Revises: d260326a1bcd
Create Date: 2026-03-26 13:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "e2c7a1c9f0ab"
down_revision = "d260326a1bcd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_bind_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("qr_url", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bound_user_id", sa.String(length=128), nullable=True),
        sa.Column("bound_open_user_id", sa.String(length=128), nullable=True),
        sa.Column("callback_raw", sa.Text(), nullable=True),
        sa.Column("fail_reason", sa.String(length=256), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wecom_bind_sessions_instance_id", "wecom_bind_sessions", ["instance_id"], unique=False)
    op.create_index("ix_wecom_bind_sessions_org_id", "wecom_bind_sessions", ["org_id"], unique=False)
    op.create_index("ix_wecom_bind_sessions_user_id", "wecom_bind_sessions", ["user_id"], unique=False)
    op.create_index("ix_wecom_bind_sessions_state", "wecom_bind_sessions", ["state"], unique=False)
    op.create_index("ix_wecom_bind_sessions_status", "wecom_bind_sessions", ["status"], unique=False)
    op.create_index("ix_wecom_bind_sessions_deleted_at", "wecom_bind_sessions", ["deleted_at"], unique=False)
    op.create_index(
        "ix_wecom_bind_sessions_instance_user_status",
        "wecom_bind_sessions",
        ["instance_id", "user_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_wecom_bind_sessions_state_active",
        "wecom_bind_sessions",
        ["state"],
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_wecom_bind_sessions_state_active", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_instance_user_status", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_deleted_at", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_status", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_state", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_user_id", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_org_id", table_name="wecom_bind_sessions")
    op.drop_index("ix_wecom_bind_sessions_instance_id", table_name="wecom_bind_sessions")
    op.drop_table("wecom_bind_sessions")
