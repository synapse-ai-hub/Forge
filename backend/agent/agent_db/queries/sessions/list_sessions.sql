-- List root sessions ordered by most recent activity (sub-agent
-- sessions and the transient sessions of the workflow generator are
-- excluded from the sidebar list).
SELECT session_id, created_at, updated_at, metadata, title
FROM sessions
WHERE parent_id IS NULL AND session_id NOT LIKE 'workflow-generate:%'
ORDER BY updated_at DESC;
