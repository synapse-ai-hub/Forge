-- Tool result message fallback when tool_call_id is NULL (legacy rows
-- dispatched before ids were synthesized for id-less providers).
SELECT tool_name, content, status FROM messages
WHERE session_id = ? AND role = 'tool' AND turn_number = ? AND step = ? AND tool_name = ?
ORDER BY id DESC LIMIT 1;
