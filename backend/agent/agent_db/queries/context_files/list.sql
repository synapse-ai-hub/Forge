-- List stored context files (newest first).
SELECT id, filename, created_at FROM context_files ORDER BY created_at DESC;
