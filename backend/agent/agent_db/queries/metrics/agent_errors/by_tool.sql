-- Failed tool calls grouped by tool name: the ones of the agents (messages, filtered by the creation
-- time of their session) and, in the workflows (workflow_runs, filtered by the time the row started:
-- a run has no session), the nodes that run a tool and the tools an agent node called.
-- {TIME_CLAUSE} : filter on created_at.
SELECT m.tool AS tool, COUNT(*) AS cnt
FROM (
    SELECT messages.tool_name AS tool, sessions.created_at AS created_at
    FROM messages JOIN sessions ON sessions.session_id = messages.session_id
    WHERE messages.role = 'tool' AND messages.status = 'error' AND messages.tool_name IS NOT NULL
    UNION ALL
    SELECT tool_name AS tool, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('node', 'tool') AND tool_name IS NOT NULL AND status = 'error'
) m
WHERE 1=1 {TIME_CLAUSE}
GROUP BY m.tool
ORDER BY cnt DESC;
