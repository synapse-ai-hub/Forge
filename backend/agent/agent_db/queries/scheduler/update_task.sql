-- Update a scheduled task and reset its last run date.
UPDATE scheduled_tasks SET
name = ?, prompt = ?, time = ?, days = ?, enabled = ?,
repetitions = ?, tool_permissions = ?, skill_permissions = ?,
parameters = ?, last_run_date = NULL, updated_at = ? WHERE id = ?;
