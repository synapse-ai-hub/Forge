-- Whether the scheduler already started a run of a workflow in a minute (YYYY-MM-DDTHH:MM).
SELECT 1 FROM workflow_runs
WHERE kind = 'run' AND source = 'schedule' AND workflow_name = ? AND substr(started_at, 1, 16) = ?
LIMIT 1;
