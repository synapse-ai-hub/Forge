-- Most recent executions started by the scheduler (runs of the workflows that have a schedule).
SELECT run_id AS id, workflow_name AS task_id, workflow_name AS name, NULL AS prompt,
       status, COALESCE(result, error_text) AS detail, started_at, finished_at
FROM workflow_runs
WHERE kind = 'run' AND source = 'schedule'
ORDER BY started_at DESC LIMIT ?;
