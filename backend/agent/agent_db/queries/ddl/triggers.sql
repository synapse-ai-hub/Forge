-- Registry of proactive triggers. The YAML workflow stays the definition; the slug is the id.
-- A row is created when a trigger is created in the UI. secret_hash never leaves the backend
-- except once at creation and rotation. enabled pauses reception without deleting history.
CREATE TABLE IF NOT EXISTS triggers (
    slug TEXT PRIMARY KEY,  -- trigger id; also the path segment of its webhook URL
    workflow_name TEXT NOT NULL,  -- workflow to run; must exist in workflows(name)
    secret_hash TEXT NOT NULL,  -- hash of the trigger secret, never the secret itself
    enabled INTEGER NOT NULL DEFAULT 1,  -- 1 accepts events, 0 rejects without deleting history
    created_at TEXT NOT NULL,  -- local time the trigger was created
    updated_at TEXT NOT NULL,  -- local time of the last change
    FOREIGN KEY (workflow_name) REFERENCES workflows(name)
);

CREATE INDEX IF NOT EXISTS idx_triggers_workflow ON triggers(workflow_name);
CREATE INDEX IF NOT EXISTS idx_triggers_enabled ON triggers(enabled);
