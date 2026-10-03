-- Replace the tool_results of the assistant message of a turn.
UPDATE messages SET tool_results = ?
WHERE session_id = ? AND role = 'assistant' AND turn_number = ?;
