-- Commits of a workflow run: one row per node execution.
-- state: open (dispatched) | done (result committed) | failed | stale
--   (a done row invalidated because an earlier step had to be re-run).
-- result holds the complete node output (never truncated) so a retry or a
-- resume after a crash rebuilds the shared state without re-running it.
-- What ended is deleted: a run that finished well keeps no rows here, only a run that failed or
-- was cut leaves them to resume from. The record of everything the run did lives in
-- workflow_runs. run_id has no foreign key: it is the group of rows of workflow_runs that share
-- it, so no column is unique to reference.
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    run_id TEXT NOT NULL,  -- run the node belongs to (workflow_runs.run_id)
    attempt INTEGER NOT NULL DEFAULT 1,  -- attempt of the run that executed it
    step INTEGER NOT NULL,  -- step of the workflow (nodes of the same step run in parallel)
    substep INTEGER NOT NULL DEFAULT 0,  -- position of the node inside its step
    node_id TEXT NOT NULL,  -- id of the node in the YAML
    node_type TEXT NOT NULL,  -- agent | tool | rag | run
    args TEXT,  -- JSON with the arguments of the node
    state TEXT NOT NULL DEFAULT 'open',  -- open | done | failed | stale
    result TEXT,  -- complete output of the node
    error TEXT,  -- failure message when state is failed
    child_session_id TEXT,  -- session of the sub-agent, in agent nodes
    created_at TEXT NOT NULL,  -- local time the node was dispatched
    updated_at TEXT NOT NULL  -- local time of the last change
);

CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run ON workflow_run_steps(run_id, step);
