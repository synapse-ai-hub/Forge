-- Total response quality votes in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT COUNT(*) AS cnt
FROM message_feedback
WHERE 1=1 {TIME_CLAUSE};
