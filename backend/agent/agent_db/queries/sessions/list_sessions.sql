-- List root sessions ordered by most recent activity (sub-agent
-- sessions are excluded from the sidebar list).
SELECT session_id, created_at, updated_at, metadata, title
FROM sessions WHERE parent_id IS NULL ORDER BY updated_at DESC;
