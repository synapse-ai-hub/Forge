-- All non-empty session titles of root sessions (title generation guard).
SELECT title FROM sessions
WHERE title IS NOT NULL AND title != '' AND parent_id IS NULL;
