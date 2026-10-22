-- Time per tool call (seconds): the execution time of each individual tool call, of the agents
-- (messages, filtered by the creation time of their session) and, in the workflows (workflow_runs,
-- filtered by the time the row started: a run has no session), of the nodes that run a tool and the
-- tools an agent node called. NULL times are excluded so they never count as 0.
-- {TIME_CLAUSE} : filter on sessions.created_at; the rows below are named "sessions" so that column
-- is the time each row is filtered by.
SELECT sessions.total_time AS total_time
FROM (
    SELECT messages.total_time AS total_time, s.created_at AS created_at
    FROM messages JOIN sessions s ON s.session_id = messages.session_id
    WHERE messages.tool_name IS NOT NULL AND messages.tool_name != ''
    UNION ALL
    SELECT total_time, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('node', 'tool') AND tool_name IS NOT NULL
) sessions
WHERE sessions.total_time IS NOT NULL {TIME_CLAUSE};
