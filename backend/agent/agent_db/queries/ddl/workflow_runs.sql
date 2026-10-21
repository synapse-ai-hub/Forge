-- One row per workflow execution.
-- status: running | success | error | cancelled
-- source: play (UI button) | tool (called by an agent through the workflow tool)
-- attempt: current attempt, 1..3 (the run resumes from the last committed node).
-- result: final answer of the run. error_text: plain-language failure explanation.
-- Spend of the LLM calls the engine makes by itself (judge, explain, output), not the
-- agent nodes (their cost lives in their child sessions): the tokens/cost columns hold the
-- sum for the run, like a messages row, and usage_calls keeps every call as JSON
-- ([{purpose, provider, model, prompt_tokens, completion_tokens, total_tokens, total_time,
-- cost_input, cost_output, cost_total, created_at}]). spend is NOT touched here:
-- llm_process already contemplates it.
CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    session_id TEXT,
    parent_session_id TEXT,
    source TEXT NOT NULL DEFAULT 'play',
    status TEXT NOT NULL DEFAULT 'running',
    attempt INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    result TEXT,
    error_text TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_time REAL NOT NULL DEFAULT 0,
    cost_input REAL NOT NULL DEFAULT 0,
    cost_output REAL NOT NULL DEFAULT 0,
    cost_total REAL NOT NULL DEFAULT 0,
    usage_calls TEXT,
    FOREIGN KEY (workflow_name) REFERENCES workflows(name)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON workflow_runs(workflow_name);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at);
