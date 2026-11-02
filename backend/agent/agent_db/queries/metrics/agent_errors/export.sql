-- Agent errors in the time range (CSV export): messages with status 'error'.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT session_id, turn_number, provider, model, tool_name, message, created_at
FROM messages
WHERE status = 'error' {TIME_CLAUSE}
ORDER BY created_at ASC;
