-- Every stage execution of a delivery, in order.
SELECT * FROM trigger_run_steps WHERE event_id = ? ORDER BY id ASC;
