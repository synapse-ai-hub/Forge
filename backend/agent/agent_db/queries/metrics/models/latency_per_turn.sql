-- Latency per turn, attributed to the turn's model.
-- Each turn has a single model (the assistant row), so the turn latency
-- is attributed to that model. A turn may have several assistant rows
-- (one per step), so we pick a single representative (MAX id) to avoid
-- duplicating the latency value. NULL latency is never counted.
-- {TIME_CLAUSE} : filter on sessions.created_at.
-- {MODEL_CLAUSE} : optional filter on m.model / m.provider.
SELECT t.latency AS latency
FROM turn_latency t
JOIN (
    SELECT session_id, turn_number, model, provider
    FROM messages
    WHERE role = 'assistant'
        AND model IS NOT NULL
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
  {MODEL_CLAUSE}