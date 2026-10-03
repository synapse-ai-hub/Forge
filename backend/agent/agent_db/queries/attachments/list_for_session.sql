-- Attachment rows of a session (file name and size per turn).
SELECT turn_number, file_name, size FROM attachments
WHERE session_id = ? ORDER BY turn_number, id;
