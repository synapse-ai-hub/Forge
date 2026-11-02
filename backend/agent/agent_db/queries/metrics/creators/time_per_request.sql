-- Time (seconds) per creator request in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT creator_id AS sid, total_time AS value
FROM creators
WHERE role = 'result' AND creator_id IS NOT NULL AND total_time IS NOT NULL {TIME_CLAUSE};
