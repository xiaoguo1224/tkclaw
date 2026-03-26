create table if not exists wecom_bind_sessions (
    id varchar(36) primary key,
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

create index if not exists ix_wecom_bind_sessions_instance_id on wecom_bind_sessions(instance_id);
create index if not exists ix_wecom_bind_sessions_org_id on wecom_bind_sessions(org_id);
create index if not exists ix_wecom_bind_sessions_user_id on wecom_bind_sessions(user_id);
create index if not exists ix_wecom_bind_sessions_state on wecom_bind_sessions(state);
create index if not exists ix_wecom_bind_sessions_status on wecom_bind_sessions(status);
create index if not exists ix_wecom_bind_sessions_deleted_at on wecom_bind_sessions(deleted_at);
create index if not exists ix_wecom_bind_sessions_instance_user_status
    on wecom_bind_sessions(instance_id, user_id, status);

create unique index if not exists uq_wecom_bind_sessions_state_active
    on wecom_bind_sessions(state)
    where deleted_at is null;
