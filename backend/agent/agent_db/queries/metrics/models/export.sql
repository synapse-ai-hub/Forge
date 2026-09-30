-- Assistant LLM calls per message in the time range (CSV export).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT session_id, turn_number, provider, model, created_at
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != '' {TIME_CLAUSE}
ORDER BY created_at ASC;