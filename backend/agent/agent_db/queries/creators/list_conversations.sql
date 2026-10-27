-- Conversations of one kind of creator, most recent first (the history sidebar).
SELECT c.creator_id,
       c.kind,
       MIN(c.created_at) AS created_at,
       MAX(c.created_at) AS updated_at,
       (SELECT u.content FROM creators u
         WHERE u.creator_id = c.creator_id AND u.role = 'user' ORDER BY u.id LIMIT 1) AS first_message,
       (SELECT r.item_name FROM creators r
         WHERE r.creator_id = c.creator_id AND r.role = 'result' AND r.item_name IS NOT NULL
         ORDER BY r.id DESC LIMIT 1) AS item_name,
       (SELECT r.status FROM creators r
         WHERE r.creator_id = c.creator_id AND r.role = 'result' ORDER BY r.id DESC LIMIT 1) AS status
FROM creators c
WHERE c.creator_id IS NOT NULL AND c.kind = ? AND c.role IN ('user', 'assistant', 'tool', 'result')
GROUP BY c.creator_id
ORDER BY updated_at DESC
LIMIT ?;
