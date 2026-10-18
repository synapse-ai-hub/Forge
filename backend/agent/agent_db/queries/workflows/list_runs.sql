-- Most recent runs (optionally of one workflow: pass NULL for all).
SELECT * FROM workflow_runs
WHERE (? IS NULL OR workflow_name = ?)
ORDER BY started_at DESC LIMIT ?;
