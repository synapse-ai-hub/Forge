-- Remove the notifications of a deleted scheduled task.
DELETE FROM notifications WHERE task_id = ?;
