-- Creator requests per kind (agent | skill | tool | workflow) in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT kind, COUNT(*) AS cnt
FROM creators
WHERE role = 'result' AND kind IS NOT NULL AND kind != '' {TIME_CLAUSE}
GROUP BY kind
ORDER BY cnt DESC;
