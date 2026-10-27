-- Tool result message matched by exact tool_call_id (creators table).
SELECT tool_name, content, status FROM creators
WHERE creator_id = ? AND role = 'tool' AND tool_call_id = ?
ORDER BY id DESC LIMIT 1;
