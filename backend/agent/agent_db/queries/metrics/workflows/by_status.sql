-- Workflow runs per status (running | success | error | cancelled) in the time range.
-- {TIME_CLAUSE} : filter on started_at.
SELECT status, COUNT(*) AS cnt
FROM workflow_runs
WHERE kind = 'run' AND status IS NOT NULL AND status != '' {TIME_CLAUSE}
GROUP BY status
ORDER BY cnt DESC;
