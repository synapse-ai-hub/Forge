-- Response quality votes in the time range (CSV export).
-- {TIME_CLAUSE} : filter on created_at.
SELECT session_id, turn_number, feedback_type, provider, model, created_at, updated_at
FROM message_feedback
WHERE 1=1 {TIME_CLAUSE}
ORDER BY created_at ASC;
