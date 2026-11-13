-- Start another attempt of a delivery (it stays in progress).
UPDATE trigger_runs SET attempt = ?, status = 'received', finished_at = NULL WHERE event_id = ?;
