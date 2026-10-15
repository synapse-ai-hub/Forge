-- Tool result message matched by exact tool_call_id.
SELECT tool_name, content, status FROM messages
WHERE session_id = ? AND role = 'tool' AND tool_call_id = ?
ORDER BY id DESC LIMIT 1;
