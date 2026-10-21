-- Spend of a sub-agent session: the sum of its messages and the model of the last one that has it.
SELECT
    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
    COALESCE(SUM(total_tokens), 0) AS total_tokens,
    COALESCE(SUM(total_time), 0) AS total_time,
    COALESCE(SUM(cost_input), 0) AS cost_input,
    COALESCE(SUM(cost_output), 0) AS cost_output,
    COALESCE(SUM(cost_total), 0) AS cost_total,
    (SELECT model FROM messages WHERE session_id = ? AND model IS NOT NULL ORDER BY id DESC LIMIT 1) AS model,
    (SELECT provider FROM messages WHERE session_id = ? AND provider IS NOT NULL ORDER BY id DESC LIMIT 1) AS provider
FROM messages WHERE session_id = ?;
