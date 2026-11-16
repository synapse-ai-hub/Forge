-- One row per accepted webhook delivery, laid out like workflow_runs.
-- event_id is the public id returned with 202. trigger_slug links to triggers(slug).
-- workflow_run_id links to workflow_runs.run_id without a hard FK, like notifications.run_id,
-- because workflow_runs has many rows per run and no column is unique to reference.
-- status: received | verified | mapped | launched | notified | error.
-- attempt: delivery attempt that made the row, 1..3. idempotency_key + payload_hash
-- enforce idempotency: same key and same hash returns the original event, same key
-- with different hash is a conflict and never runs.
CREATE TABLE IF NOT EXISTS trigger_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id; orders the rows
    event_id TEXT NOT NULL,  -- public id of the delivery, returned with 202
    trigger_slug TEXT NOT NULL,  -- trigger that received the event
    workflow_name TEXT NOT NULL,  -- workflow mapped at reception time
    workflow_run_id TEXT,  -- workflow_runs.run_id of the launched run, when any
    status TEXT NOT NULL,  -- received | verified | mapped | launched | notified | error
    attempt INTEGER NOT NULL DEFAULT 1,  -- attempt that made the row, 1..3
    idempotency_key TEXT,  -- client key for idempotent retries
    payload_hash TEXT,  -- hash of the raw body, to detect conflicting reuse
    result TEXT,  -- short result of the linked run, when finished
    error_text TEXT,  -- failure message in plain language, when failed
    started_at TEXT NOT NULL,  -- local time the event was accepted
    finished_at TEXT,  -- local time the pipeline closed
    FOREIGN KEY (trigger_slug) REFERENCES triggers(slug),
    FOREIGN KEY (workflow_name) REFERENCES workflows(name)
);

CREATE INDEX IF NOT EXISTS idx_trigger_runs_event ON trigger_runs(event_id);
CREATE INDEX IF NOT EXISTS idx_trigger_runs_trigger ON trigger_runs(trigger_slug);
CREATE INDEX IF NOT EXISTS idx_trigger_runs_status ON trigger_runs(status);
CREATE INDEX IF NOT EXISTS idx_trigger_runs_started_at ON trigger_runs(started_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trigger_runs_idempotency ON trigger_runs(trigger_slug, idempotency_key) WHERE idempotency_key IS NOT NULL;
