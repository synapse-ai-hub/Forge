<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Checkpoints — synapseForge</h1>

---

Tests del sistema de checkpoints (`step_frontier`) contra el flujo real: el mismo bot que usa `tests/e2e` maneja el chat por SSE, y además cada escenario aserta sobre la `agent.db` real del backend — qué se trackeó, qué dejó un corte y qué borró el cierre validado. Nada mockeado. Aserta sobre **estructura del contrato y estado de DB**, nunca sobre texto exacto del modelo.

---

## Requisitos

- Python 3.11+
- Paquetes: `pip install requests pyyaml`
- El backend corriendo **en esta misma máquina** (`python -m uvicorn backend.main:app --reload` o `run`), porque el runner lee su SQLite directamente
- LLM configurado: necesario para los dos escenarios (el modelo tiene que despachar tool calls reales)

| Grupo | Backend local | LLM configurado |
|-------|:-------------:|:---------------:|
| **checkpoints** (2) | ✅ | ✅ (los dos escenarios) |

---

## Uso

### Directo con el runner

```bash
# Todos los escenarios
python -m tests.checkpoints.runner

# Filtrar por nombre (substring match)
python -m tests.checkpoints.runner --only cut-flow
python -m tests.checkpoints.runner --only clean-close

# Apuntar a otro backend (la DB se lee de --db-path)
python -m tests.checkpoints.runner --base-url http://192.168.1.100:8000 --db-path ./otro/agent.db
```

---

## Escenarios disponibles

| Escenario | Qué verifica |
|-----------|--------------|
| `checkpoint-clean-close-leaves-no-frontier` | Bloque paralelo real termina con `[DONE]` y el cierre validado deja la frontera en 0 filas |
| `checkpoint-cut-flow-leaves-open-frontier` | Corte a mitad del bloque deja filas `open`; el turno siguiente cierra lo suyo sin borrar el pendiente anterior |

---

## Formato de escenarios YAML

Igual que `tests/e2e` (`chat` con `message`, `session`, `abort_after_events`, `expect`), más el paso `db_assert` que inspecciona la `agent.db` real:

```yaml
scenario: nombre-unico-del-escenario
description: Que verifica este escenario.
cleanup: true
steps:
  - action: chat
    message: "Inspeccioná los directorios 'backend' y 'frontend'..."
    session: cut
    abort_after_events: 3
    expect:
      done: true
      parallel_block: true
  - action: db_assert
    session: cut
    expect:
      total_rows: 0    # cantidad exacta de filas de la sesión
      open_min: 1      # al menos N filas todavía open
      turn_empty: 2    # ningún resto del turno N
```

---

## Reportes

Cada ejecución genera un JSON en `tests/checkpoints/reports/` con timestamp, resultados por escenario y duración.
