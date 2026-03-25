CREATE TABLE IF NOT EXISTS workspace_departments (
    workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
    department_id VARCHAR(36) NOT NULL REFERENCES departments(id),
    org_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
    id VARCHAR(36) PRIMARY KEY,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_workspace_departments_deleted_at
    ON workspace_departments (deleted_at);

CREATE INDEX IF NOT EXISTS ix_workspace_departments_workspace_id
    ON workspace_departments (workspace_id);

CREATE INDEX IF NOT EXISTS ix_workspace_departments_department_id
    ON workspace_departments (department_id);

CREATE INDEX IF NOT EXISTS ix_workspace_departments_org_id
    ON workspace_departments (org_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_department_link
    ON workspace_departments (workspace_id, department_id)
    WHERE deleted_at IS NULL;

INSERT INTO workspace_departments (
    id,
    workspace_id,
    department_id,
    org_id,
    created_at,
    updated_at
)
SELECT
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
FROM workspaces w
CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(w.allowed_department_ids, '[]'::jsonb)) AS dep(department_id)
LEFT JOIN workspace_departments wd
    ON wd.workspace_id = w.id
   AND wd.department_id = dep.department_id
   AND wd.deleted_at IS NULL
WHERE w.deleted_at IS NULL
  AND dep.department_id IS NOT NULL
  AND wd.id IS NULL;
