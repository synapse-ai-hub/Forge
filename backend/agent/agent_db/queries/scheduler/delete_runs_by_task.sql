-- Delete the recorded runs of a task.
DELETE FROM task_runs WHERE task_id = ?;
