<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Decisor — synapseForge</h1>

---

Prueba manual por CLI del modelo de decisión (`Agent.decision`), manejada por YAML sin argumentos: los escenarios viven en `scenarios/decisor.yaml` (un documento por prueba, más un documento `config` con los sleeps) y el CLI los corre todos en orden. Test limpio: cada escenario pasa el prompt completo en `prompt` y va a `state` verbatim, sin agregados internos. Solo se suma lo hardcodeado a nivel instrucciones (sección `## Tarea` por modo, y solo en las corridas con `compare: true`). Guarda un reporte Markdown verbatim más un `.json` con los datos de la tabla, y agrega una línea por modelo a `report/general.jsonl`. El recreador del prompt del agente padre vive aparte en `parent_state.py` (misma carpeta, independiente del test).

---

## Requisitos

- Python 3.12+
- Paquetes: `typesafe-sdk` (ya incluido en el venv del proyecto)
- API Key de OpenRouter guardada en la app (**Configuración → Providers**). Sin ella, la llamada devuelve `available: false` y el reporte lo registra igual.
- No requiere backend corriendo (usa el código directo, no HTTP).

---

## Uso

```bash
# Corre todos los escenarios de scenarios/decisor.yaml (sin argumentos)
python -m tests.decisor.decision_cli
```

Cada escenario del YAML (separados por número de prueba):

```yaml
config:
  sleep_entre_llamadas: 30
  sleep_entre_escenarios: 30
---
scenario: prueba1
mode: score
prompt: |
  Prompt completo (va a state verbatim, sin agregados).
score: "muy malo,malo,aceptable,bueno,excelente"
instructions: ""
compare: true
file: prueba1
```

| Campo | Descripción |
|-----------|-------------|
| `scenario` | Nombre de la prueba (también key `prueba` en `general.jsonl`). |
| `mode` | Modalidad, una sola por escenario (sin default): `noul`, `choice` o `score`. |
| `prompt` | Prompt completo (requerido, va a `state` verbatim, sin agregados). |
| `file` | Solo el nombre, sin `.md` (por defecto con timestamp). |
| `noul` | Pregunta sí/no con estas instrucciones (requerido con `mode: noul`). |
| `choice` | Pregunta choice con opciones `clave=descripción;...` (requerido con `mode: choice`). |
| `score` | Pregunta score con niveles separados por coma, ej: `"muy malo,malo,aceptable,bueno,excelente"` (requerido con `mode: score`). |
| `instructions` | Instrucciones para `choice` / `score`. |
| `compare` | Si es `true`, además corre la prueba contra cuatro LLM tradicionales vía `Agent.llm_process` (`gemini-3.5-flash-lite` en `google`, `openai/gpt-oss-20b` en `groq`, `inclusionai/ling-3.1-flash` en `openrouter` y `qwen/qwen3.8-27b` en `groq`) y agrega tabla comparativa. Requiere `GOOGLE_API_KEY`, `GROQ_API_KEY` y `OPENROUTER_API_KEY` en el entorno. |
| `config.sleep_entre_llamadas` | Segundos de espera entre llamadas a modelos (por rate limit). |
| `config.sleep_entre_escenarios` | Segundos de espera entre escenarios. |

---

## Prompt del agente padre (`parent_state.py`)

Recrea el prompt del agente padre con el código real (system vía `build_system_prompt(None)`, con las secciones de todas las tools, más sección de directorio temporal, array real de tools según permisos y catálogo de skills) y lo imprime por stdout. Independiente del test: su salida sirve para alimentar `-p` en corridas de benchmark.

```bash
python tests/decisor/parent_state.py -p "mensaje del usuario"
```

---

## Comparación (`compare: true`)

Con el flag, después del modelo de decisión se llama a `Agent.llm_process` con cada uno de los cuatro modelos, con el mismo `state` del usuario más una sección `## Tarea` en texto según el modo: con `mode: choice` le indica elegir, en base al prompt y a la solicitud del usuario, una de las opciones de `choice` (solo ese listado, sin el JSON del modelo de decisión); con `mode: score` le indica asignar un puntaje en base a los criterios de `score` pasados como diccionario `0..N-1 → descripción` (armado automáticamente según la cantidad de niveles, misma escala del modelo de decisión) y devolver solo el número (float, puede caer entre niveles); con `mode: noul` le indica responder solo la pregunta de `noul`. En los tres casos el texto hardcodeado ordena devolver solo eso, sin texto extra, sin argumentar. El reporte agrega solo la sección agregada (la tarea), una sección de respuesta por modelo (una por cada id de modelo) y al final una tabla con las mismas columnas y valores del `.json` (`proveedor`, `modelo`, `tokens_entrada`, `tokens_salida`, `tiempo`, `decision`, `gasto_usd`). Sin el flag, la tabla trae solo la fila del modelo de decisión.

---

## Reportes

Cada escenario genera un `.md` en `tests/decisor/report/` con el prompt exacto del modelo de decisión (el texto `state` completo tal como viaja en el body del request, en texto plano sin transformar), la sección agregada para LLM tradicionales (solo con `compare: true`), los parámetros, la respuesta del modelo de decisión, una sección de respuesta por cada modelo comparado (solo con `compare: true`, una por cada id de modelo) y la tabla comparativa. Con el mismo nombre se guarda además un `.json` en la misma carpeta con los datos de la tabla (proveedor, modelo, tokens de entrada/salida, tiempo, decisión y gasto). Además, cada fila se agrega a `report/general.jsonl` (una línea por modelo) con los mismos campos del `.json` más `prueba` (nombre del escenario) y `tipo` (`noul`, `choice` o `score`).
