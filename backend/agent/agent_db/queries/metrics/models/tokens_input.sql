-- Sum of input (prompt) tokens per provider/model in the time range.
-- Rows with NULL or 0 tokens (failed turn, never loaded) are excluded:
-- a 0 is never a real count and would pollute averages.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT provider, model, SUM(prompt_tokens) AS value
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != ''
    AND prompt_tokens > 0 {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY value DESC;