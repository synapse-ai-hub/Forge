-- Total workflow runs in the time range (one row per run).
-- {TIME_CLAUSE} : filter on started_at.
SELECT COUNT(*) AS cnt
FROM workflow_runs
WHERE kind = 'run' {TIME_CLAUSE};
