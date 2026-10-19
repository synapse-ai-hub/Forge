-- Registry of workflows. The YAML file stays the definition; the name is the id.
-- A row is created the first time a workflow is saved or run.
CREATE TABLE IF NOT EXISTS workflows (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
