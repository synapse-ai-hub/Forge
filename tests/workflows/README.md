<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Workflows — synapseForge</h1>

---

Tests end-to-end de los workflows deterministas: validación del esquema, guardado, selección y ejecución real contra el backend. Usan la misma metodología declarativa que `tests/e2e` (endpoints reales, sin mocks) y aserta sobre **estructura del contrato**, nunca sobre texto exacto del modelo.

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
```

---

## Escenarios disponibles

| Archivo | Escenarios |
|---------|-----------|
| `workflows.yaml` | `workflow-validate-ok`, `workflow-validate-sin-final`, `workflow-validate-run-ok`, `workflow-validate-run-workdir-traversal`, `workflow-save-y-seleccion`, `workflow-save-nombre-invalido`, `workflow-select-inexistente`, `workflow-generate-sin-descripcion` |
| `workflows_run.yaml` | `workflow-run-echo-e2e`, `workflow-faltantes-amigable` |

| Escenario | Qué verifica |
|-----------|--------------|
| `workflow-validate-*` | `POST /api/config/workflows/validate` acepta un workflow correcto y un nodo `run`, y rechaza un workflow sin nodo `final` y un `workdir` con traversal |
| `workflow-save-y-seleccion` | Un workflow guardado aparece en `available` y queda activo al seleccionarlo |
| `workflow-save-nombre-invalido` | El guardado rechaza nombres inválidos |
| `workflow-select-inexistente` | Seleccionar un workflow que no existe devuelve error |
| `workflow-generate-sin-descripcion` | La generación exige una descripción |
| `workflow-run-echo-e2e` | Un workflow con un nodo `run` se ejecuta, termina con `[DONE]` y responde con contenido |
| `workflow-faltantes-amigable` | Un workflow que referencia una tool inexistente no se ejecuta y el chat responde «No se puede ejecutar» |

---

## Formato de escenarios YAML

Igual que `tests/e2e` (`chat`, `request`, `expect`), más dos extensiones propias de este runner:

```yaml
scenario: nombre-unico-del-escenario
description: Qué verifica este escenario.
cleanup: true                      # vuelve la selección a smart al terminar
verify:
  workflow: e2e-test-workflow      # debe figurar en selection.available
  selected: e2e-test-workflow      # opcional: debe ser selection.selected
steps:
  - action: chat
    message: "ejecutá el workflow"
    expect:
      done: true
      response_contains: ["No se puede ejecutar"]   # substrings en el texto final
```

---

## Reportes

Cada ejecución genera un JSON en `tests/workflows/reports/` con timestamp, totales y resultados por escenario. La carpeta no está versionada.

Los escenarios de guardado escriben archivos `e2e-*.yaml` en `~/.config/synapseForge/workflows/` y no hay endpoint para borrarlos: se sobrescriben en cada corrida.
