-- Commits of a trigger pipeline: one row per stage execution.
-- state: open (dispatched) | done (result committed) | failed | stale
--   (a done row invalidated because an earlier stage had to be re-run).
-- result holds the complete stage output (never truncated) so a retry or a
-- resume after a crash rebuilds the pipeline without re-running it.
-- What ended is deleted: a delivery that finished well keeps no rows here, only a delivery that failed or
-- was cut leaves them to resume from. The record of everything the delivery did lives in
-- trigger_runs. event_id has no foreign key: it is the group id of trigger_runs that share
-- it, so no column is unique to reference.
CREATE TABLE IF NOT EXISTS trigger_run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    event_id TEXT NOT NULL,  -- delivery the stage belongs to (trigger_runs.event_id)
    attempt INTEGER NOT NULL DEFAULT 1,  -- attempt of the delivery that executed it
    step INTEGER NOT NULL,  -- stage of the pipeline (received, verified, mapped, launched, notified)
    substep INTEGER NOT NULL DEFAULT 0,  -- position of the stage inside its step
    node_id TEXT NOT NULL,  -- id of the stage in the pipeline
    node_type TEXT NOT NULL,  -- received | verified | mapped | launched | notified
    args TEXT,  -- JSON with the arguments of the stage
    state TEXT NOT NULL DEFAULT 'open',  -- open | done | failed | stale
    result TEXT,  -- complete output of the stage
    error TEXT,  -- failure message when state is failed
    created_at TEXT NOT NULL,  -- local time the stage was dispatched
    updated_at TEXT NOT NULL  -- local time of the last change
);

CREATE INDEX IF NOT EXISTS idx_trigger_run_steps_run ON trigger_run_steps(event_id, step);
