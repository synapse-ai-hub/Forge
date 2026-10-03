<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests E2E — synapseForge</h1>

---

Tests end-to-end declarativos basados en escenarios YAML. Cada escenario ejecuta el mismo flujo que usa el frontend (SSE chat + REST API), colecta los eventos crudos y aserta sobre **estructura del contrato**, nunca sobre texto exacto del modelo.

---

## Requisitos

- Python 3.11+
- Paquetes: `pip install requests pyyaml`
- El backend corriendo (`python -m uvicorn backend.main:app --reload` o `run`)

### Por grupo de escenarios

| Grupo | Backend | API Key OpenRouter | LLM configurado |
|-------|:-------:|:------------------:|:---------------:|
| **scheduler** (3) | ✅ | — | — |
| **creators** (5) | ✅ | — | solo `creators-chat-delegates-to-agent` |
| **main_flow** (3) | ✅ | — | — |
| **rag** (3) | ✅ | ✅ | solo `rag-chat-search-memory-available` |
| **parallel** (2) | ✅ | — | ✅ (los dos escenarios) |

- **API Key de OpenRouter**: necesaria para los tests de RAG. Se carga desde **Configuración → Providers** en la UI. Sin ella, los endpoints RAG devuelven error al intentar instanciar ChromaDB.
- **LLM configurado**: necesario para los escenarios de chat que hacen streaming SSE.

---

## Uso

### Comando rápido

```bash
# Todos los escenarios
test

# Filtrar por nombre (substring match)
test rag
test scheduler
test creators
test main-flow

# Apuntar a otro backend
test rag --url http://192.168.1.100:8000
```

### Directo con el runner

```bash
# Todos los escenarios
python -m tests.e2e.runner

# Filtrar por nombre
python -m tests.e2e.runner --only rag
python -m tests.e2e.runner --only scheduler

# Apuntar a otro backend
python -m tests.e2e.runner --base-url http://127.0.0.1:8000
```

---

## Escenarios disponibles

| Archivo | Escenarios |
|---------|-----------|
| `rag.yaml` | `rag-create-list-delete-collection`, `rag-rejects-invalid-name`, `rag-chat-search-memory-available` |
| `scheduler.yaml` | `scheduler-create-toggle-delete`, `scheduler-rejects-invalid-task`, `scheduler-delete-nonexistent` |
| `creators.yaml` | `creators-list-agents`, `creators-list-tools`, `creators-list-skills`, `creators-delete-nonexistent-skill`, `creators-chat-delegates-to-agent` |
| `main_flow.yaml` | `main-flow-basic-chat`, `main-flow-with-attachment-context`, `main-flow-cancel-stream` |
| `parallel.yaml` | `parallel-two-list-dir-same-block`, `parallel-three-list-dir-same-block` |

---

## Formato de escenarios YAML

```yaml
scenario: nombre-unico-del-escenario
description: Que verifica este escenario.
cleanup: true
steps:
  - action: chat                    # o "request"
    message: "Hola"
    session: s1                     # alias de sesión (opcional)
    expect:
      done: true
      nonempty: true
      no_tool_error: true
```

---

## Reportes

Cada ejecución genera un JSON en `tests/e2e/reports/` con timestamp, resultados por escenario y duración.
