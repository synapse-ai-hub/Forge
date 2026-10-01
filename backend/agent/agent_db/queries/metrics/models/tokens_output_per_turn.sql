-- Output (completion) tokens per turn, attributed to the turn's model.
-- A turn may have several assistant rows (one per step); we sum completion_tokens
-- across the turn. NULL and 0 completion_tokens (failed turn, never loaded)
-- are never counted: a 0 would pollute the average.
-- {TIME_CLAUSE} : filter on sessions.created_at.
-- {MODEL_CLAUSE} : optional filter on m.model / m.provider.
SELECT SUM(msg.completion_tokens) AS value
FROM messages msg
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
  ON m.session_id = msg.session_id
 AND m.turn_number = msg.turn_number
WHERE msg.role = 'assistant'
  AND msg.completion_tokens > 0
  AND msg.session_id IN (SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE})
  {MODEL_CLAUSE}
GROUP BY msg.session_id, msg.turn_number