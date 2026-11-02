-- Response quality votes per type (up | down) in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT feedback_type, COUNT(*) AS cnt
FROM message_feedback
WHERE feedback_type IS NOT NULL AND feedback_type != '' {TIME_CLAUSE}
GROUP BY feedback_type
ORDER BY cnt DESC;
