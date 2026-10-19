-- Latest run of every workflow.
SELECT r.* FROM workflow_runs r
JOIN (
    SELECT workflow_name, MAX(started_at) AS last_started
    FROM workflow_runs GROUP BY workflow_name
) l ON l.workflow_name = r.workflow_name AND l.last_started = r.started_at;
