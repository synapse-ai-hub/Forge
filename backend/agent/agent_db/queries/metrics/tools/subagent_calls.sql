-- Sub-agent delegations: how many times each sub-agent was called through the 'task' tool
-- (the agent_name argument of each call, read from the tool_calls JSON of the assistant messages).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COALESCE(json_extract(j.value, '$.args.agent_name'), '(sin nombre)') AS agent_name, COUNT(*) AS cnt
FROM messages, json_each(messages.tool_calls) AS j
WHERE messages.tool_calls LIKE '%"task"%'
    AND json_valid(messages.tool_calls)
    AND json_extract(j.value, '$.name') = 'task' {TIME_CLAUSE}
GROUP BY agent_name
ORDER BY cnt DESC;
