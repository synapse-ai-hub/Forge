-- Top 5 tools by call count in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT tool_name, COUNT(*) AS cnt
FROM messages
WHERE tool_name IS NOT NULL AND tool_name != '' {TIME_CLAUSE}
GROUP BY tool_name
ORDER BY cnt DESC
LIMIT 5;
