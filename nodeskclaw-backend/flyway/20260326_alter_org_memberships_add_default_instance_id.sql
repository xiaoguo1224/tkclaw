alter table org_memberships
    add column if not exists default_instance_id varchar(36) null references instances(id);

create index if not exists ix_org_memberships_default_instance_id
    on org_memberships(default_instance_id);
