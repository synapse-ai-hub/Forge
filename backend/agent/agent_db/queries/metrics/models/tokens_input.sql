-- Sum of input (prompt) tokens per provider/model in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT provider, model, SUM(prompt_tokens) AS value
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != ''
    AND prompt_tokens IS NOT NULL {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY value DESC;