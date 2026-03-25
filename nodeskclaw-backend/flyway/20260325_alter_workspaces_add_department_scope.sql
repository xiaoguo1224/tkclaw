alter table workspaces
    add column if not exists visibility_scope varchar(32) not null default 'org';

alter table workspaces
    add column if not exists allowed_department_ids jsonb not null default '[]'::jsonb;

alter table workspaces
    add column if not exists auto_sync_mode varchar(32) not null default 'manual';
