-- List root sessions ordered by most recent activity (sub-agent
-- sessions, the transient sessions of the workflow generator and the
-- sessions of workflow runs and scheduled tasks are excluded from the
-- sidebar list: they are read from the notification and only become a
-- conversation when the user reviews them with the agent).
SELECT session_id, created_at, updated_at, metadata, title
FROM sessions
WHERE parent_id IS NULL AND session_id NOT LIKE 'workflow-generate:%'
  AND (metadata IS NULL OR NOT json_valid(metadata)
       OR COALESCE(json_extract(metadata, '$.source'), '') NOT IN ('workflow', 'scheduler'))
ORDER BY updated_at DESC;
