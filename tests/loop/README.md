<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Loop — synapseForge</h1>

---

Tests del loop del agente (`AgentLoop.run`) sin base de datos ni LLM.

---

## Requisitos

- Python 3.12+
- `pytest`
- No requiere backend, LLM ni API keys.

---

## Uso

```bash
pytest tests/loop
```

---

## Tests disponibles

| Test | Qué verifica |
|------|--------------|
| `test_exit_before_the_title_step_ends_the_stream_without_error` | Una salida temprana de `run` (acá, el límite de profundidad de sub-agentes), anterior a la generación del título, termina el stream con `[DONE]` y sin errores |
