-- Open a trigger delivery (status received, attempt 1).
INSERT INTO trigger_runs (event_id, trigger_slug, workflow_name, status, attempt, idempotency_key, payload_hash, started_at)
VALUES (?, ?, ?, 'received', 1, ?, ?, ?);
