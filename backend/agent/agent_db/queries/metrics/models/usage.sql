-- Assistant LLM calls per model in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT model, COUNT(*) AS cnt
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != '' {TIME_CLAUSE}
GROUP BY model
ORDER BY cnt DESC;
