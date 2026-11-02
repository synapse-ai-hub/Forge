-- Workflow runs per workflow name in the time range.
-- {TIME_CLAUSE} : filter on started_at.
SELECT workflow_name, COUNT(*) AS cnt
FROM workflow_runs
WHERE kind = 'run' {TIME_CLAUSE}
GROUP BY workflow_name
ORDER BY cnt DESC;
