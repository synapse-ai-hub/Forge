-- Remove the node commits of one finished run (what ended is deleted, like step_frontier).
DELETE FROM workflow_run_steps WHERE run_id = ?;
