-- Remove the feedback of an answer.
DELETE FROM message_feedback WHERE session_id = ? AND turn_number = ?;
