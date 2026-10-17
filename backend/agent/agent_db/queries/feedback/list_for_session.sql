-- Feedback of every answer of a session.
SELECT turn_number, feedback_type FROM message_feedback
WHERE session_id = ? ORDER BY turn_number;
