-- Persist the slot_runs JSON of a task.
UPDATE scheduled_tasks SET slot_runs = ? WHERE id = ?;
