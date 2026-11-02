-- Workflow runs in the time range (CSV export, one row per run).
-- {TIME_CLAUSE} : filter on started_at.
SELECT run_id, workflow_name, source, status, attempt, total_tokens, total_time, cost_total, started_at, finished_at
FROM workflow_runs
WHERE kind = 'run' {TIME_CLAUSE}
ORDER BY started_at ASC;
