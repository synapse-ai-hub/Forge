-- Sub-agent delegations: call count of the 'task' tool.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT tool_name, COUNT(*) AS cnt
FROM messages
WHERE tool_name = 'task' {TIME_CLAUSE}
GROUP BY tool_name;
