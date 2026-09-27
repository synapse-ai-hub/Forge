-- Insert one row into the error log.
INSERT INTO error_log
    (session_id, parent_id, turn_number, exception, source, created_at)
VALUES (?, ?, ?, ?, ?, ?);
