-- Average turn latency per session, taken directly from the turn_latency
-- table (written once per finished turn). One row per session; sessions
-- with no latency rows are omitted. NULL latencies are excluded so they
-- never count as 0 in the average.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT t.session_id AS sid, AVG(t.latency) AS avg_lat
FROM turn_latency t
WHERE t.latency IS NOT NULL
  AND t.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY t.session_id;
