-- Record a non-LLM usage call (embeddings, transcription).
INSERT INTO external_usage
(kind, provider, model, units, prompt_tokens,
 completion_tokens, duration, session_id, turn_number, step, created_at)
VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?);
