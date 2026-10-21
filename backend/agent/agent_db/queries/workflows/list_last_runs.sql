-- Latest run of every workflow.
SELECT r.run_id AS id, r.workflow_name, r.session_id, r.parent_session_id, r.source, r.status, r.attempt, r.started_at, r.finished_at, r.result, r.error_text
FROM workflow_runs r
JOIN (
    SELECT workflow_name, MAX(started_at) AS last_started
    FROM workflow_runs WHERE kind = 'run' GROUP BY workflow_name
) l ON l.workflow_name = r.workflow_name AND l.last_started = r.started_at
WHERE r.kind = 'run';
