-- Create a scheduled task (enabled by default).
INSERT INTO scheduled_tasks
(id, name, prompt, time, days, enabled, repetitions,
 tool_permissions, skill_permissions, parameters,
 slot_runs, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, '{}', ?, ?);
