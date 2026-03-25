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

create index if not exists ix_department_memberships_deleted_at on department_memberships(deleted_at);
create index if not exists ix_department_memberships_org_id on department_memberships(org_id);
create index if not exists ix_department_memberships_user_id on department_memberships(user_id);
create index if not exists ix_department_memberships_department_id on department_memberships(department_id);

create unique index if not exists uq_department_membership_user_department
    on department_memberships(user_id, department_id)
    where deleted_at is null;

create unique index if not exists uq_department_membership_primary_org_user
    on department_memberships(org_id, user_id)
    where deleted_at is null and is_primary = true;
