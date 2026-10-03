-- Tool calls per provider/model in the time range.
-- Tool rows inherit the provider/model of the turn that chose them.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT provider, model, COUNT(*) AS value
FROM messages
WHERE role = 'tool'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != '' {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY value DESC;