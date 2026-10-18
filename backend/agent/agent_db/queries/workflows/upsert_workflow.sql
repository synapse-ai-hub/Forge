-- Register a workflow (created on first save or run), touching updated_at otherwise.
INSERT INTO workflows (name, created_at, updated_at) VALUES (?, ?, ?)
ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at;
