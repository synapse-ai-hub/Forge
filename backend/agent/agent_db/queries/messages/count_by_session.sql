-- Message count of a session.
SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?;
