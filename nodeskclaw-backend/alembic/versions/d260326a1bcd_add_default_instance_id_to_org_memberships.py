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
    op.execute(
        """
        alter table org_memberships
            add column if not exists default_instance_id varchar(36);
        """
    )
    op.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'fk_org_memberships_default_instance_id'
            ) then
                alter table org_memberships
                    add constraint fk_org_memberships_default_instance_id
                    foreign key (default_instance_id) references instances(id);
            end if;
        end
        $$;
        """
    )
    op.execute(
        """
        create index if not exists ix_org_memberships_default_instance_id
            on org_memberships(default_instance_id);
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_org_memberships_default_instance_id;")
    op.execute(
        """
        alter table org_memberships
            drop constraint if exists fk_org_memberships_default_instance_id;
        """
    )
    op.execute(
        """
        alter table org_memberships
            drop column if exists default_instance_id;
        """
    )
