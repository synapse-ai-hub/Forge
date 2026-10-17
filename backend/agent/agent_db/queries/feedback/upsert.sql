-- Save the feedback of an answer, or change it if the answer already has one.
INSERT INTO message_feedback
(session_id, turn_number, feedback_type, model, provider, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(session_id, turn_number) DO UPDATE SET
    feedback_type = excluded.feedback_type,
    updated_at = excluded.updated_at;
