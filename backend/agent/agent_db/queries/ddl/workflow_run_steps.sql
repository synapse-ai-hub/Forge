-- Commits of a workflow run: one row per node execution.
-- state: open (dispatched) | done (result committed) | failed | stale
--   (a done row invalidated because an earlier step had to be re-run).
-- result holds the complete node output (never truncated) so a retry or a
-- resume after a crash rebuilds the shared state without re-running it.
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    step INTEGER NOT NULL,
    substep INTEGER NOT NULL DEFAULT 0,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    args TEXT,
    state TEXT NOT NULL DEFAULT 'open',
    result TEXT,
    error TEXT,
    child_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run ON workflow_run_steps(run_id, step);
