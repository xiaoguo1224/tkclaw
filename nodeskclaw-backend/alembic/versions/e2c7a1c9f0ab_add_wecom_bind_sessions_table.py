"""add wecom bind sessions table

Revision ID: e2c7a1c9f0ab
Revises: d260326a1bcd
Create Date: 2026-03-26 13:10:00
"""

from alembic import op


revision = "e2c7a1c9f0ab"
down_revision = "d260326a1bcd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists wecom_bind_sessions (
            id varchar(36) not null primary key,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            deleted_at timestamptz null,
            instance_id varchar(36) not null references instances(id),
            org_id varchar(36) not null references organizations(id),
            user_id varchar(36) not null references users(id),
            state varchar(96) not null,
            status varchar(16) not null default 'pending',
            qr_url text not null,
            expires_at timestamptz not null,
            bound_user_id varchar(128) null,
            bound_open_user_id varchar(128) null,
            callback_raw text null,
            fail_reason varchar(256) null,
            bound_at timestamptz null,
            cancelled_at timestamptz null
        );
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_instance_id
            on wecom_bind_sessions(instance_id);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_org_id
            on wecom_bind_sessions(org_id);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_user_id
            on wecom_bind_sessions(user_id);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_state
            on wecom_bind_sessions(state);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_status
            on wecom_bind_sessions(status);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_deleted_at
            on wecom_bind_sessions(deleted_at);
        """
    )
    op.execute(
        """
        create index if not exists ix_wecom_bind_sessions_instance_user_status
            on wecom_bind_sessions(instance_id, user_id, status);
        """
    )
    op.execute(
        """
        create unique index if not exists uq_wecom_bind_sessions_state_active
            on wecom_bind_sessions(state)
            where deleted_at is null;
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists uq_wecom_bind_sessions_state_active;")
    op.execute("drop index if exists ix_wecom_bind_sessions_instance_user_status;")
    op.execute("drop index if exists ix_wecom_bind_sessions_deleted_at;")
    op.execute("drop index if exists ix_wecom_bind_sessions_status;")
    op.execute("drop index if exists ix_wecom_bind_sessions_state;")
    op.execute("drop index if exists ix_wecom_bind_sessions_user_id;")
    op.execute("drop index if exists ix_wecom_bind_sessions_org_id;")
    op.execute("drop index if exists ix_wecom_bind_sessions_instance_id;")
    op.execute("drop table if exists wecom_bind_sessions;")
