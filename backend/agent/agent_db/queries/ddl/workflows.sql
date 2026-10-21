-- Registry of workflows. The YAML file stays the definition; the name is the id.
-- A row is created the first time a workflow is saved or run.
CREATE TABLE IF NOT EXISTS workflows (
    name TEXT PRIMARY KEY,  -- workflow name; also the name of its YAML file
    created_at TEXT NOT NULL,  -- local time the workflow was registered
    updated_at TEXT NOT NULL  -- local time of the last change
);
