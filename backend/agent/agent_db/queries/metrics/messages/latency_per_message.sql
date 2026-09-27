-- Latency per message (turn), taken directly from the turn_latency table.
-- NULL latencies (a part of the turn was never loaded) are excluded so
-- they never count as 0 in the average.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT t.session_id AS sid, t.turn_number AS turn, t.latency AS latency
FROM turn_latency t
WHERE t.latency IS NOT NULL
AND t.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
);
