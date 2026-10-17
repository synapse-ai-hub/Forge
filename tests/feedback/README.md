<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Feedback — synapseForge</h1>

---

Tests del 👍/👎 sobre las respuestas del asistente. Usan el router real de `backend.routes.feedback` (con `TestClient`), el `SessionManager` real y `AgentLoop.run` real contra una base SQLite aislada en una carpeta temporal, así que el `agent.db` del usuario nunca se toca.

---

## Requisitos

- Python 3.12+
- `pytest`
- No requiere backend corriendo ni API keys.

---

## Uso

```bash
pytest tests/feedback
pytest tests/feedback -v
```

---

## Tests disponibles

| Test | Qué verifica |
|------|--------------|
| `test_save_read_change_and_remove_feedback` | Guardar, leer, cambiar y quitar el feedback de una respuesta por `PUT`, `GET` y `DELETE` |
| `test_feedback_keeps_the_model_that_answered` | El feedback guarda el modelo y el proveedor que generaron la respuesta |
| `test_invalid_requests_are_rejected_and_save_nothing` | Un tipo inválido, una sesión inexistente o un turno sin respuesta se rechazan y no guardan nada |
| `test_deleting_the_session_deletes_its_feedback` | Borrar la sesión borra su feedback |
| `test_the_loop_announces_the_turn_before_anything_else` | El loop emite el evento SSE `turn` antes que cualquier otro evento |
