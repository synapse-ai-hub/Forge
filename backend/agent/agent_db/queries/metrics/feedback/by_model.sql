-- Response quality votes per provider/model in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT provider, model, feedback_type, COUNT(*) AS cnt
FROM message_feedback
WHERE provider IS NOT NULL AND model IS NOT NULL {TIME_CLAUSE}
GROUP BY provider, model, feedback_type
ORDER BY cnt DESC;
