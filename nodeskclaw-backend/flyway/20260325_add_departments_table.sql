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

create index if not exists ix_departments_deleted_at on departments(deleted_at);
create index if not exists ix_departments_org_id on departments(org_id);
create index if not exists ix_departments_parent_id on departments(parent_id);

create unique index if not exists uq_department_org_slug
    on departments(org_id, slug)
    where deleted_at is null;
