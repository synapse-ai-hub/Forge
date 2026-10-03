-- Store the computed latency of a finished turn.
INSERT INTO turn_latency (session_id, turn_number, latency) VALUES (?, ?, ?);
