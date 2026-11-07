-- Fetch a delivery by its idempotency key for duplicate detection.
SELECT id, event_id, trigger_slug, workflow_name, workflow_run_id, status, attempt, idempotency_key, payload_hash, result, error_text, started_at, finished_at
FROM trigger_runs WHERE trigger_slug = ? AND idempotency_key = ?;
