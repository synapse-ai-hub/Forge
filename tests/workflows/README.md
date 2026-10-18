<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Workflows — synapseForge</h1>

---

Tests de los workflows deterministas: validación del esquema, guardado, listado y ejecución real (play, reintentos, cancelación, notificaciones). Hay dos capas: escenarios end-to-end contra el backend (misma metodología declarativa que `tests/e2e`: endpoints reales, sin mocks, aserciones sobre **estructura del contrato**, nunca sobre texto exacto del modelo) y tests de pytest contra una base y una carpeta de workflows aisladas.

---

## Requisitos

- Python 3.12+
- Paquetes: `pip install requests pyyaml`
- El backend corriendo (`python -m uvicorn backend.main:app --reload` o `run`)
- No requiere LLM configurado: ningún escenario depende de un modelo.

---

## Uso

```bash
# Todos los escenarios
python -m tests.workflows.runner

# Un escenario por nombre
python -m tests.workflows.runner --only workflow-validate-ok

# Apuntar a otro backend
python -m tests.workflows.runner --base-url http://192.168.1.100:8000

# Tests de pytest (base y carpeta de workflows temporales, tardan ~1 minuto por los reintentos)
pytest tests/workflows/test_workflow_runs.py
```

Los escenarios `workflow-fallo-reintenta` y `workflow-cancelar` usan comandos de shell (`exit 3`, `python -c ...`): el backend necesita `python` en el PATH.

---

## Escenarios disponibles

| Archivo | Escenarios |
|---------|-----------|
| `workflows.yaml` | `workflow-validate-ok`, `workflow-validate-sin-final`, `workflow-validate-run-ok`, `workflow-validate-run-workdir-traversal`, `workflow-save-y-listado`, `workflow-save-nombre-invalido`, `workflow-run-inexistente`, `workflow-generate-sin-descripcion` |
| `workflows_run.yaml` | `workflow-run-echo-e2e`, `workflow-faltantes-amigable`, `workflow-fallo-reintenta`, `workflow-cancelar` |

| Escenario | Qué verifica |
|-----------|--------------|
| `workflow-validate-*` | `POST /api/config/workflows/validate` acepta un workflow correcto y un nodo `run`, y rechaza un workflow sin nodo `final` y un `workdir` con traversal |
| `workflow-save-y-listado` | Un workflow guardado aparece en `GET /api/workflows` |
| `workflow-save-nombre-invalido` | El guardado rechaza nombres inválidos |
| `workflow-run-inexistente` | Ejecutar un workflow que no existe devuelve 404 |
| `workflow-generate-sin-descripcion` | La generación exige una descripción |
| `workflow-run-echo-e2e` | Un workflow con un nodo `run` se ejecuta con play, termina en éxito al primer intento con el resultado del comando y genera su notificación |
| `workflow-faltantes-amigable` | Un workflow que referencia una tool inexistente no se ejecuta, no crea ningún run y el play responde «No se puede ejecutar» |
| `workflow-fallo-reintenta` | Un comando que termina con código distinto de cero falla el nodo; el run se reintenta hasta 3 intentos y termina en error con su notificación |
| `workflow-cancelar` | Cancelar un run en curso lo deja como `cancelled` y no genera notificación |

---

## Formato de escenarios YAML

Igual que `tests/e2e` (`request`, `expect`), más la acción `run` y el bloque `verify` propios de este runner:

```yaml
scenario: nombre-unico-del-escenario
description: Qué verifica este escenario.
cleanup: true                      # borra las notificaciones y las sesiones de run que creó
verify:
  workflow: e2e-test-workflow      # debe figurar en GET /api/workflows
steps:
  - action: run                    # el botón play
    workflow: e2e-run-echo
    timeout: 120                   # segundos de espera a que termine el run
    cancel_after: 1.5              # opcional: cancela a los N segundos
    expect:
      http_status: 200             # del play (por defecto 200)
      message_contains: ["No se puede ejecutar"]   # substrings del mensaje del play
      run_status: success          # success | error | cancelled
      attempts: 3                  # intento en el que terminó
      result_contains: ["hola"]    # substrings del resultado del run
      error_contains: ["..."]      # substrings de la explicación del error
      notification: true           # existe una notificación del run (false: ninguna)
```

---

## Reportes

Cada ejecución genera un JSON en `tests/workflows/reports/` con timestamp, totales y resultados por escenario. La carpeta no está versionada.

Los escenarios de guardado escriben archivos `e2e-*.yaml` en `~/.config/synapseForge/workflows/` y no hay endpoint para borrarlos: se sobrescriben en cada corrida. Las notificaciones y las sesiones de run que crean se eliminan al terminar (`cleanup`); las filas de `workflow_runs` quedan como historial.
