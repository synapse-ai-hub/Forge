-- Models with latency data per provider/model in the time range.
-- Only turns with a non-NULL latency are counted (NULL is never a 0).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.provider AS provider, m.model AS model, COUNT(*) AS value
FROM turn_latency t
JOIN (
    SELECT session_id, turn_number, model, provider
    FROM messages
    WHERE role = 'assistant'
        AND model IS NOT NULL AND model != ''
        AND provider IS NOT NULL AND provider != ''
        AND id IN (
            SELECT MAX(id)
            FROM messages
            WHERE role = 'assistant' AND model IS NOT NULL
            GROUP BY session_id, turn_number
        )
) m
  ON m.session_id = t.session_id
 AND m.turn_number = t.turn_number
WHERE t.latency IS NOT NULL
  AND t.session_id IN (SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE})
GROUP BY m.provider, m.model
ORDER BY value DESC;