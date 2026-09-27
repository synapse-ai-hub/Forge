-- Most recent task executions joined with task name and prompt.
SELECT r.*, t.prompt, t.name FROM task_runs r
LEFT JOIN scheduled_tasks t ON t.id = r.task_id
ORDER BY r.started_at DESC LIMIT ?;
