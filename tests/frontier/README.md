<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Frontier — synapseForge</h1>

---

Tests unitarios de la frontera de tool calls (`step_frontier`) y de los gates de cierre. Ejercitan las funciones reales de `backend/agent/utils/frontier_helpers.py` y `decision.py` contra una base SQLite aislada creada con `setup_database`. Sin red y sin backend.

---

## Requisitos

- Python 3.12+
- `pytest`
- No requiere backend, LLM ni API keys.

---

## Uso

```bash
pytest tests/frontier
pytest tests/frontier -v
```

---

## Tests disponibles

| Test | Qué verifica |
|------|--------------|
| `test_ddl_creates_step_frontier` | El DDL crea la tabla vacía |
| `test_dispatch_writes_open_rows_with_full_args` | El despacho escribe una fila `open` por call, con los argumentos completos |
| `test_mark_done_flips_only_matching_row` | `mark_call_done` pasa a `done` solo la fila indicada y no falla con una inexistente |
| `test_clear_turn_deletes_only_that_turn` | `clear_turn` borra únicamente el turno indicado |
| `test_cut_flow_leaves_open_rows_until_close` | Un corte deja filas `open`; el cierre validado las borra |
| `test_extract_task_child_id_from_result_xml` | Se extrae el id de la sub-sesión del resultado de `task` |
| `test_set_task_child_attaches_child_id` | El id de la sub-sesión se asocia a la fila |
| `test_build_resume_message_reads_first` | El mensaje de reanudación incluye pedido original, argumentos y resultado completos |
| `test_build_resume_message_none_when_clean` | Sin pendientes no se genera mensaje |
| `test_should_close_accepts_llm_without_decisor` | Sin modelo de decisión, `should_close_step` acepta la señal del LLM |
| `test_should_close_fail_open_on_decision_error` | Si el modelo de decisión falla, `should_close_step` cierra el paso |
| `test_collect_garbage_deletes_only_old_done` | El GC borra solo filas `done` vencidas y nunca las `open` |

Los escenarios contra el flujo real (backend, LLM y `agent.db`) están en `tests/checkpoints/`.
