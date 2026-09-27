-- Average turn latency across all sessions in the range, taken directly
-- from the turn_latency table (NULL latencies are skipped by AVG).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT AVG(t.latency) AS avg_latency
FROM turn_latency t
WHERE t.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
);
