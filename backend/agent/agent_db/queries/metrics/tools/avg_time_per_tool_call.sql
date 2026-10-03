-- Average execution time of a tool call (seconds).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT AVG(total_time) AS avg
FROM messages
WHERE tool_name IS NOT NULL AND tool_name != ''
    AND total_time IS NOT NULL {TIME_CLAUSE};
