-- Total execution/LLM time (seconds) in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT SUM(total_time) AS total
FROM messages
WHERE total_time IS NOT NULL {TIME_CLAUSE};
