-- Remove the stage commits of one finished delivery (what ended is deleted).
DELETE FROM trigger_run_steps WHERE event_id = ?;
