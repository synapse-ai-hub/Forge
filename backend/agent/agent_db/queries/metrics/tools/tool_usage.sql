-- Tool usage: call count and average execution time per tool name.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT tool_name, COUNT(*) AS cnt, AVG(total_time) AS avg_time
FROM messages
WHERE tool_name IS NOT NULL AND tool_name != '' {TIME_CLAUSE}
GROUP BY tool_name
ORDER BY cnt DESC;
