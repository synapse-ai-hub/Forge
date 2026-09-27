-- Read the slot_runs JSON of a task (per-slot dedup).
SELECT slot_runs FROM scheduled_tasks WHERE id = ?;
