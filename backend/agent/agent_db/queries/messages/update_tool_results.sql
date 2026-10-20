-- Replace the tool_results of the assistant message of a turn step.
-- A NULL step updates every assistant message of the turn.
UPDATE messages SET tool_results = ?
WHERE session_id = ? AND role = 'assistant' AND turn_number = ?
  AND (? IS NULL OR step = ?);
