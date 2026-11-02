-- Cost (USD) per workflow run in the time range (sum of its rows).
-- {TIME_CLAUSE} : filter on started_at.
SELECT run_id AS sid, SUM(cost_total) AS value
FROM workflow_runs
WHERE 1=1 {TIME_CLAUSE}
GROUP BY run_id;
