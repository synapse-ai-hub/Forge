-- Assistant LLM calls with cost in the time range (CSV export).
-- Rows with NULL or 0 cost (failed turn or model without rate) are excluded.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT session_id, turn_number, provider, model,
       cost_input, cost_output, cost_total, created_at
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != ''
    AND cost_total > 0 {TIME_CLAUSE}
ORDER BY created_at ASC;
