-- First user message content of a session (chat preview/title source).
SELECT content FROM messages
WHERE session_id = ? AND role = 'user'
ORDER BY id ASC LIMIT 1;
