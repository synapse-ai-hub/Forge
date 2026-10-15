-- Garbage-collect confirmed rows older than the TTL cutoff (ISO timestamp).
-- Open rows are never collected: they are unsettled work a future turn resumes.
DELETE FROM step_frontier WHERE state = 'done' AND updated_at < ?;
