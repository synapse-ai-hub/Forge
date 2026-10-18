-- Runs still marked as running (active now, or cut by a backend crash).
SELECT * FROM workflow_runs WHERE status = 'running' ORDER BY started_at ASC;
