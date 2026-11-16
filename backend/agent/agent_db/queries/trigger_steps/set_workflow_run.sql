-- Link a delivery with the launched workflow run.
UPDATE trigger_runs SET workflow_run_id = ? WHERE event_id = ?;
