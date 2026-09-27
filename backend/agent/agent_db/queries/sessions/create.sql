-- Insert a new session row (sub-agent sessions carry parent_id).
INSERT INTO sessions (session_id, created_at, updated_at, metadata, parent_id)
VALUES (?, ?, ?, ?, ?);
