-- Token totals (total/prompt/completion) in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT SUM(total_tokens) AS total,
       SUM(prompt_tokens) AS prompt,
       SUM(completion_tokens) AS completion
FROM messages
WHERE total_tokens IS NOT NULL {TIME_CLAUSE};
