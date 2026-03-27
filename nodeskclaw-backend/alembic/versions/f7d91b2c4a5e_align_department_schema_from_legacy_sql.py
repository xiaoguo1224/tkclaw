"""align department schema from legacy sql

Revision ID: f7d91b2c4a5e
Revises: e2c7a1c9f0ab
Create Date: 2026-03-27 15:40:00
"""

from alembic import op


revision = "f7d91b2c4a5e"
down_revision = "e2c7a1c9f0ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists departments (
            id varchar(36) primary key,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            deleted_at timestamptz null,
            org_id varchar(36) not null references organizations(id),
            parent_id varchar(36) null references departments(id),
            name varchar(128) not null,
            slug varchar(128) not null,
            description varchar(512) not null default '',
            sort_order integer not null default 0,
            is_active boolean not null default true
        );
        """
    )
    op.execute("create index if not exists ix_departments_deleted_at on departments(deleted_at);")
    op.execute("create index if not exists ix_departments_org_id on departments(org_id);")
    op.execute("create index if not exists ix_departments_parent_id on departments(parent_id);")
    op.execute(
        """
        create unique index if not exists uq_department_org_slug
            on departments(org_id, slug)
            where deleted_at is null;
        """
    )

    op.execute(
        """
        create table if not exists department_memberships (
            id varchar(36) primary key,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            deleted_at timestamptz null,
            org_id varchar(36) not null references organizations(id),
            user_id varchar(36) not null references users(id),
            department_id varchar(36) not null references departments(id),
            role varchar(16) not null default 'member',
            is_primary boolean not null default false
        );
        """
    )
    op.execute("create index if not exists ix_department_memberships_deleted_at on department_memberships(deleted_at);")
    op.execute("create index if not exists ix_department_memberships_org_id on department_memberships(org_id);")
    op.execute("create index if not exists ix_department_memberships_user_id on department_memberships(user_id);")
    op.execute("create index if not exists ix_department_memberships_department_id on department_memberships(department_id);")
    op.execute(
        """
        create unique index if not exists uq_department_membership_user_department
            on department_memberships(user_id, department_id)
            where deleted_at is null;
        """
    )
    op.execute(
        """
        create unique index if not exists uq_department_membership_primary_org_user
            on department_memberships(org_id, user_id)
            where deleted_at is null and is_primary = true;
        """
    )

    op.execute(
        """
        alter table workspaces
            add column if not exists visibility_scope varchar(32) not null default 'org';
        """
    )
    op.execute(
        """
        alter table workspaces
            add column if not exists allowed_department_ids jsonb not null default '[]'::jsonb;
        """
    )
    op.execute(
        """
        alter table workspaces
            add column if not exists auto_sync_mode varchar(32) not null default 'manual';
        """
    )

    op.execute(
        """
        create table if not exists workspace_departments (
            workspace_id varchar(36) not null references workspaces(id),
            department_id varchar(36) not null references departments(id),
            org_id varchar(36) not null references organizations(id),
            id varchar(36) primary key,
            deleted_at timestamptz null,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );
        """
    )
    op.execute("create index if not exists ix_workspace_departments_deleted_at on workspace_departments(deleted_at);")
    op.execute("create index if not exists ix_workspace_departments_workspace_id on workspace_departments(workspace_id);")
    op.execute("create index if not exists ix_workspace_departments_department_id on workspace_departments(department_id);")
    op.execute("create index if not exists ix_workspace_departments_org_id on workspace_departments(org_id);")
    op.execute(
        """
        create unique index if not exists uq_workspace_department_link
            on workspace_departments(workspace_id, department_id)
            where deleted_at is null;
        """
    )

    op.execute(
        """
        insert into workspace_departments (
            id,
            workspace_id,
            department_id,
            org_id,
            created_at,
            updated_at
        )
        select
            (
                substr(md5(random()::text || clock_timestamp()::text || w.id || dep.department_id), 1, 8) || '-' ||
                substr(md5(random()::text || clock_timestamp()::text || w.id || dep.department_id), 9, 4) || '-' ||
                substr(md5(random()::text || clock_timestamp()::text || w.id || dep.department_id), 13, 4) || '-' ||
                substr(md5(random()::text || clock_timestamp()::text || w.id || dep.department_id), 17, 4) || '-' ||
                substr(md5(random()::text || clock_timestamp()::text || w.id || dep.department_id), 21, 12)
            ),
            w.id,
            dep.department_id,
            w.org_id,
            now(),
            now()
        from workspaces w
        cross join lateral jsonb_array_elements_text(coalesce(w.allowed_department_ids, '[]'::jsonb)) as dep(department_id)
        left join workspace_departments wd
            on wd.workspace_id = w.id
           and wd.department_id = dep.department_id
           and wd.deleted_at is null
        where w.deleted_at is null
          and dep.department_id is not null
          and wd.id is null;
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists uq_workspace_department_link;")
    op.execute("drop index if exists ix_workspace_departments_org_id;")
    op.execute("drop index if exists ix_workspace_departments_department_id;")
    op.execute("drop index if exists ix_workspace_departments_workspace_id;")
    op.execute("drop index if exists ix_workspace_departments_deleted_at;")
    op.execute("drop table if exists workspace_departments;")

    op.execute("alter table workspaces drop column if exists auto_sync_mode;")
    op.execute("alter table workspaces drop column if exists allowed_department_ids;")
    op.execute("alter table workspaces drop column if exists visibility_scope;")

    op.execute("drop index if exists uq_department_membership_primary_org_user;")
    op.execute("drop index if exists uq_department_membership_user_department;")
    op.execute("drop index if exists ix_department_memberships_department_id;")
    op.execute("drop index if exists ix_department_memberships_user_id;")
    op.execute("drop index if exists ix_department_memberships_org_id;")
    op.execute("drop index if exists ix_department_memberships_deleted_at;")
    op.execute("drop table if exists department_memberships;")

    op.execute("drop index if exists uq_department_org_slug;")
    op.execute("drop index if exists ix_departments_parent_id;")
    op.execute("drop index if exists ix_departments_org_id;")
    op.execute("drop index if exists ix_departments_deleted_at;")
    op.execute("drop table if exists departments;")
