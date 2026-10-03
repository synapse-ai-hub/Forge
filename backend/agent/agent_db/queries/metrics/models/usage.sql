-- Assistant LLM calls per provider/model in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT provider, model, COUNT(*) AS cnt
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != '' {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY cnt DESC;