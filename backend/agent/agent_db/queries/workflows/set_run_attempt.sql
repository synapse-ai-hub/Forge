-- Start another attempt of a run (it stays running).
UPDATE workflow_runs SET attempt = ?, status = 'running', finished_at = NULL WHERE id = ?;
