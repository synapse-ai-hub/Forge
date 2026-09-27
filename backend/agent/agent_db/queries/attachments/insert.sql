-- Store an attachment (binary content included) for a message turn.
INSERT INTO attachments (session_id, turn_number, file_name, size, content, created_at)
VALUES (?, ?, ?, ?, ?, ?);
