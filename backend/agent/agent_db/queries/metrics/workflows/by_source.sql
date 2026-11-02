-- Workflow runs per source (play | tool | schedule) in the time range.
-- {TIME_CLAUSE} : filter on started_at.
SELECT source, COUNT(*) AS cnt
FROM workflow_runs
WHERE kind = 'run' AND source IS NOT NULL AND source != '' {TIME_CLAUSE}
GROUP BY source
ORDER BY cnt DESC;
