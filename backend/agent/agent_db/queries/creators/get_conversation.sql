-- Every row of a creator conversation except the LLM calls, in order.
SELECT * FROM creators
WHERE creator_id = ? AND role IN ('user', 'assistant', 'tool', 'result')
ORDER BY id;
