-- Tool result message fallback when tool_call_id is NULL (Google wire format).
SELECT tool_name, content, status FROM messages
WHERE session_id = ? AND role = 'tool' AND turn_number = ? AND step = ? AND tool_name = ?
ORDER BY id DESC LIMIT 1;
