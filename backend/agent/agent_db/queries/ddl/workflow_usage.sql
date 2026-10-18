-- Spend of the LLM calls the workflow engine makes by itself (not the agent
-- nodes, whose cost lives in their child sessions).
-- purpose: judge (did the run finish well) | explain (plain-language failure).
-- spend is NOT touched here: llm_process already contemplates it.
CREATE TABLE IF NOT EXISTS workflow_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_time REAL,
    cost_input REAL DEFAULT 0.0,
    cost_output REAL DEFAULT 0.0,
    cost_total REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_name) REFERENCES workflows(name),
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_usage_run ON workflow_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_usage_name ON workflow_usage(workflow_name);
