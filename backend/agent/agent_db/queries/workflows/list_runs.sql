-- Most recent runs (optionally of one workflow: pass NULL for all).
SELECT run_id AS id, workflow_name, parent_session_id, source, status, attempt, started_at, finished_at, result, error_text
FROM workflow_runs
WHERE kind = 'run' AND (? IS NULL OR workflow_name = ?)
ORDER BY started_at DESC LIMIT ?;
