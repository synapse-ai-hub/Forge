-- Tool calls in the time range (CSV export).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT session_id, turn_number, tool_name, total_time, created_at
FROM messages
WHERE tool_name IS NOT NULL AND tool_name != '' {TIME_CLAUSE}
ORDER BY created_at ASC;