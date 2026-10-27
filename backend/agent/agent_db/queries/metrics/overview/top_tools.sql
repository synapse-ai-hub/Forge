-- Top 5 tools by call count in the time range: the tool calls of the agents (messages) and, in the
-- workflows (workflow_runs), the nodes that run a tool and the tools an agent node called.
-- {TIME_CLAUSE} : filter on created_at.
SELECT tool_name, COUNT(*) AS cnt
FROM (
    SELECT tool_name, created_at FROM messages
    WHERE tool_name IS NOT NULL AND tool_name != ''
    UNION ALL
    SELECT tool_name, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('node', 'tool') AND tool_name IS NOT NULL
)
WHERE 1=1 {TIME_CLAUSE}
GROUP BY tool_name
ORDER BY cnt DESC
LIMIT 5;
