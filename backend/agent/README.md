<p align="center">
  <img src="../../src/logo_empresa.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Módulo Agent</h1>

---

<p align="center">
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0" />
  </a>
</p>

---

<h3 align="center">Agente LLM con loop iterativo, herramientas nativas y persistencia SQLite</h3>

---

## Descripción

El módulo **Agent** es el núcleo del asistente conversacional. Implementa un bucle `while(true)` que itera con el LLM usando detección nativa de tool calls, ejecuta las herramientas, persiste cada mensaje en SQLite y gestiona el contexto con compactación automática. Soporta proveedores cloud curados (OpenAI-compatibles y Google Gemini) y local (Ollama).

### ✨ Características Principales

- **Loop iterativo nativo**: Llama al LLM en un `while(true)` — si responde con `tool_calls`, las ejecuta y continúa; si responde con contenido, lo entrega y termina.
- **Persistencia SQLite**: Cada mensaje, tool call y resultado se guarda automáticamente en `agent_db/agent.db`.
- **Contexto compactable**: Gestión inteligente de tokens con estrategias configurables (ask, cod, original) y límite de turnos.
- **Soporte multi-proveedor**: Funciona con proveedores cloud curados (OpenAI-compatibles y Google Gemini) y Ollama (local) sin cambiar la lógica del loop.
- **Permisos y prompts**: Resolución dinámica de herramientas y skills desde archivos markdown de agente.
- **Configuración MCP**: `mcp.json` en `~/.config/synapseForge/` para servidores MCP (Model Context Protocol).
- **Checkpoints de flujo**: Cada tool call despachada se registra en `step_frontier`; si el flujo se corta, el trabajo sin confirmar se retoma en el turno siguiente.
- **Modelo de decisión opcional**: Un modelo de decisión (System One) valida el cierre de cada paso y la continuidad del trabajo pendiente. Deshabilitado, el flujo no hace ninguna llamada extra.
- **Workflows deterministas**: Flujos en YAML ejecutados por un runner con pasos secuenciales, nodos paralelos, reintentos y permisos mínimos.

---

## ¿Qué resuelve?

- **Persistencia de conversaciones**: No pierde el historial entre sesiones — todo queda en SQLite.
- **Ejecución autónoma de herramientas**: El agente decide qué herramientas usar según la conversación, sin intervención manual.
- **Contexto ajustable**: Evita sobrecargar el LLM con historial innecesario mediante compactación automática.
- **Separación de responsabilidades**: Cada módulo (loop, sesión, contexto, configuración, permisos) tiene una función específica y desacoplada.
- **Configuración MCP persistente**: Servidores MCP se guardan en `mcp.json` y sobreviven a reinicios.
- **Modelo/Proveedor/Contexto persistidos en SQLite**: Selección de modelo, proveedor y ventana de contexto se guardan en la tabla `config_kv` y se restauran al arrancar.

---

## Estructura del producto

### 1. `loop.py` — Bucle principal del agente

Implementa el `while(true)` orquestador:
1. Crea o recupera la sesión en SQLite.
2. Carga el historial de la conversación.
3. Construye el system prompt (base + skills).
4. Resuelve las herramientas disponibles.
5. Itera: llama al LLM → si hay `tool_calls` las ejecuta → si hay contenido lo emite como SSE y termina.
6. Persiste cada mensaje en SQLite.

Expone el método `run(session_id, message)` que retorna un `AsyncGenerator` de eventos SSE (`chunk`, `tool_call`, `tool_result`, `session_title`, `done`).

### 2. `session.py` — Persistencia SQLite

Maneja toda la interacción con la base de datos SQLite:
- Creación y recuperación de sesiones.
- Guardado y carga de mensajes con tool calls y resultados.
- Almacenamiento de configuración clave/valor (`config_kv`): modelo seleccionado, proveedor, ventana de contexto.
- Path de la DB: `backend/agent/agent_db/agent.db` (relativo al project root).

### 3. `utils/config.py` — Configuración del entorno

Configuración del loop vía variables de entorno (`.env`):
- `COMPACTION_TRIGGER_TOKENS`, `COMPACTION_STRATEGY`, `COMPACTION_TAIL_TURNS`, etc.
- Dataclasses `CompactionConfig` y `SessionContext` para parámetros de compactación.

### 4. `agent.py` — Clase principal del agente

Centraliza la interacción con los proveedores LLM (proveedores cloud curados u Ollama local):
- Selección del proveedor según la configuración persistida en DB (nunca variables de entorno).
- Streaming de respuestas con detección nativa de tool calls.
- Gestión de la instancia de herramientas (`Tools`).
- Atributos runtime: `provider` (LOCAL/API), `_resolved_model` (modelo activo).

### 5. `tools.py` — Registro de herramientas

Define el catálogo completo de herramientas del agente:
- Métodos nativos (parser, websearch, webfetch, etc.).
- Carga dinámica de tools externas desde `~/.config/synapseForge/tools/`.
- Construcción del esquema function-calling para el LLM.
- Validación y ejecución de tool calls.
- Integración MCP: `execute_mcp_tool` expone herramientas de servidores MCP como tools nativas.

### 6. `permissions.py` — Permisos y prompts de agente

Resuelve en tiempo de ejecución:
- Herramientas permitidas para el agente (`get_tool_permissions`).
- Skills habilitadas (`get_skill_permissions`).
- Contenido del system prompt (`get_agent_prompt`).
- Filtrado de herramientas/skills según el agente activo.
- Permisos del agente principal (router) desde `config.yaml` (ver `loop.py`).

### 7. `utils/contract.py` — Contratos de respuesta

Define los formatos estándar de respuesta para todas las herramientas del agente:
- `make_success_response` / `make_error_response` para respuestas unificadas.
- Dataclasses `ContractResponse` y `UsageReport` para tipado estricto.
- Validación de estructura de respuesta.

### 8. `utils/` — Utilidades auxiliares

Contiene módulos de soporte genéricos para el funcionamiento del agente:
- `config.py` — Configuración del loop vía variables de entorno.
- `config_dir.py` — Gestión del directorio `~/.config/synapseForge/`.
- `contract.py` — Contratos de respuesta.
- `clean_memory.py` — Liberación de modelos de GPU/CPU.
- `model_resolver.py` — Resolución y validación del modelo activo.
- `model_catalog.py` — Catálogo de modelos sincronizado desde models.dev.
- `decision_catalog.py` — Catálogo de modelos de decisión sincronizado desde models.dev (`type=decision`).
- `decision.py` — Gates de cierre de paso y de continuidad del trabajo pendiente.
- `frontier_helpers.py` — Registro, resolución y reanudación de la frontera de tool calls.
- `workflow_loader.py`, `workflow_validator.py`, `workflow_runner.py`, `workflows_helpers.py` — Carga, validación, ejecución y helpers de workflows.
- `provider_keys.py` — Gestión de API keys (cifrado Fernet en SQLite).
- `skill_loader.py` — Carga y formateo de skills para el system prompt.
- `skills_helpers.py` — Helpers de evaluación y creación de skills.
- `email_parser.py` — Parseo de correos electrónicos (headers, body, adjuntos).
- `mcp_helper.py` — Integración con MCP (Model Context Protocol).
- `vector_db.py` — Wrapper de ChromaDB (RAG y memoria de largo plazo).
- `rag_helpers.py` — Helpers de RAG (indexación y consulta).
- `chunking.py` — División de documentos en chunks.
- `loop_helpers.py` — Helpers del loop (ejecución de tools, prompts).
- `scheduler_helpers.py` — Helpers de tareas programadas.
- `create_helpers.py` — Helpers de creación vía LLM (skills, tools, agentes).
- `tools_helpers.py` — Helpers de tools externas.
- `agent_helpers.py` — Helpers de los endpoints AgentInfo.
- `subagent_logger.py` — Logging de sub-agentes.
- `error_logger.py` — Registro de errores en `error_log`.

### 9. `prompts/` — Prompts del sistema

Almacena los prompts del agente en formato markdown:
- `system_prompt.md` — Prompt base del router.
- `mandatory.md` — Reglas `## MANDATORY:` inyectadas al final del system prompt de todos los agentes.
- `help.md` — Documentación interna para la tool `help`.
- `title.md` — Generación de títulos de sesión.
- `create_skill.md`, `create_tool.md`, `create_agent.md` — Prompts de creación vía LLM.
- `iterate_skill.md`, `iterate_tool.md`, `iterate_agent.md` — Prompts de iteración.
- `evaluate_skills.md`, `explain_skill.md` — Prompts auxiliares.
- `interview_workflow.md`, `create_workflow.md`, `iterate_workflow.md`, `generate_workflow.md` — Prompts de entrevista, creación, iteración y generación de workflows.
- `decision_close.md`, `decision_continue.md` — Instrucciones de las preguntas del modelo de decisión (cierre de paso y continuidad).

### 10. `agent_db/` — Base de datos SQLite

Directorio que contiene el archivo `agent.db` con las tablas:
- `sessions` — Metadatos de cada conversación.
- `messages` — Historial de mensajes con tool calls y resultados. El rol `decisor` guarda el veredicto del modelo de decisión y nunca se envía al LLM.
- `config_kv` — Configuración persistente (modelo, proveedor, turnos de contexto, modelo de decisión, workflow activo).
- `error_log` — Registro de excepciones del backend (session_id, turn_number, exception, source, created_at).
- `step_frontier` — Tool calls despachadas del paso en curso (`open` / `done`).
- `decision_catalog` — Modelos de decisión disponibles por proveedor, con límites, modalidades y tarifas.

El esquema se crea de forma idempotente en `ddl_setup.py` (`CREATE TABLE IF NOT EXISTS`).

### 11. Checkpoints — `utils/frontier_helpers.py`

Cada tool call despachada se registra como fila `open` en `step_frontier` antes de ejecutarse y pasa a `done` cuando su resultado se confirma. Las filas solo se borran cuando el paso cierra con una señal de fin validada; un corte (cancelación, caída) las deja para el turno siguiente.

- `record_block_dispatch` / `mark_call_done` — Registran el bloque antes de ejecutarlo y confirman cada resultado, en orden.
- `set_task_child` / `extract_task_child_id` — Enlazan la sub-sesión creada por una llamada `task` con su fila.
- `build_resume_message` — Al iniciar un turno, arma un mensaje de sistema efímero con el pedido original y las tool calls sin confirmar (argumentos y último resultado completos).
- `clear_turn` — Borra la frontera de un turno al cerrar el paso.
- `clear_session` — Borra la frontera completa de la sesión cuando el mensaje nuevo no continúa el trabajo pendiente.
- `collect_garbage` — Al iniciar cada turno borra las filas `done` más viejas que `FRONTIER_TTL_HOURS` (por defecto `24`). Las filas `open` no se recolectan.

Ninguna función de este módulo levanta excepciones: el seguimiento nunca interrumpe el loop.

### 12. Modelo de decisión — `utils/decision.py`

Un modelo de decisión (System One, vía `typesafe-sdk`) devuelve respuestas tipadas con confianza en vez de texto. `Agent.decision(state, questions)` acepta preguntas `noul`, `choice` y `score` y devuelve un `ContractResponse` con `data = {available, answers, model, provider}`. Si la sección está deshabilitada, no hay proveedor, modelo o API key, o falta el SDK, no se hace ninguna llamada y `available` es `False`.

El modelo se habilita y se elige desde la configuración, de forma independiente al modelo de chat (`config_kv`: `decision_enabled`, `decision_provider`, `decision_model`). Los modelos salen de `decision_catalog`, sincronizado desde `models.dev/api.json?type=decision` como máximo una vez cada 24 horas; mientras no haya sincronización el catálogo está vacío.

Con la sección habilitada hay dos gates, ambos de tipo `noul`:

| Gate | Cuándo corre | Qué decide |
|------|--------------|------------|
| `should_close_step` | El LLM emite una respuesta final sin tool calls | Si la frontera del turno se borra. Cierra si la confianza es `>= 0.8` (`DECISION_CLOSE_THRESHOLD`) |
| `should_keep_pending` | Al iniciar un turno con filas `open` | Si el mensaje nuevo continúa el trabajo pendiente. Descarta solo con confianza `<= 0.2` |

Ambos fallan abiertos: ante cualquier error o respuesta inválida el paso cierra y el trabajo pendiente se conserva. Cada veredicto se guarda como mensaje de rol `decisor` (`{question, type, verdict, threshold, closed | kept}`). Al descartar el pendiente, el loop emite el evento SSE `decision` con `{"action": "discarded", "reason": "unrelated"}`. Sin el modelo habilitado, `should_close_step` acepta la señal del LLM y `should_keep_pending` conserva el pendiente, sin llamadas extra. El runner de workflows usa el mismo gate de cierre.

### 13. Workflows — `utils/workflow_*.py`

Flujos deterministas definidos en archivos planos `~/.config/synapseForge/workflows/<nombre>.yaml`.

- `workflow_validator.py` — Valida el esquema: `name`, `retries` (0–10), `on_failure` (`continue` | `abort`) y nodos de tipo `agent`, `tool`, `rag` o `run`. Cada nodo tiene `id` y `step`; el workflow tiene exactamente un nodo `final: true`. Un nodo `run` ejecuta `run` (comando de shell), con `timeout` (1000–300000 ms, 30000 por defecto) y `workdir` opcional confinado al directorio del proyecto.
- `workflow_loader.py` — `list_workflows` y `load_workflow` con rechazo de nombres con `..` o separadores de ruta.
- `workflow_runner.py` — `WorkflowRunner.run` ejecuta los pasos en orden; los nodos del mismo `step` corren en paralelo con barrera. Cada nodo tiene reintentos y los de tipo `agent` corren en una sesión hija con los permisos de su agente. Las tools se habilitan con permisos mínimos: solo las que el YAML referencia (`task` nunca se habilita; la delegación se hace con nodos `agent`). Registra la frontera por paso y cierra con el mismo gate de cierre que el loop.
- `workflows_helpers.py` — Listado y evaluación de workflows para el creador y `verificar_refs`, que comprueba que existan los agentes, tools y colecciones que el workflow referencia antes de ejecutarlo.

---

## Configuración del usuario

El agente utiliza **dos fuentes de configuración** separadas:

### 1. `mcp.json` — Servidores MCP

```
~/.config/synapseForge/mcp.json
```

En Windows: `%USERPROFILE%\.config\synapseForge\mcp.json`

Este archivo almacena **exclusivamente** la configuración de servidores MCP (Model Context Protocol) como un **array** directo. Se gestiona mediante `backend/agent/config_dir.py` (funciones `load_mcp_servers()` / `save_mcp_servers()`). La conexión se realiza con el SDK oficial `mcp` (`mcp_helper.py`), con timeout por servidor y health check: si un servidor falla, se aísla y el resto del sistema sigue funcionando.

#### Estructura de `mcp.json`

```json
[
  {
    "label": "nombre-servidor",
    "transport": "stdio",
    "command": ["node", "/ruta/al/servidor/index.js"],
    "environment": {
      "API_KEY": "valor"
    }
  }
]
```

#### Campos soportados por cada servidor

| Campo | Tipo | Descripción | Default |
|-------|------|-------------|---------|
| `label` | string | Identificador único del servidor | — |
| `transport` | string | `"stdio"` (local) o `"http"` (remoto) | `"stdio"` |
| `command` | string o list | Comando o lista de comandos para ejecutar | — |
| `args` | list | Argumentos adicionales (solo si command es string) | `[]` |
| `environment` | object | Variables de entorno para el subproceso | `{}` |
| `server_url` | string | URL del servidor HTTP/SSE | — |
| `headers` | object | Cabeceras HTTP para servidores remotos | `{}` |
| `disabled` | bool | `true` para deshabilitar sin borrar | `false` |

#### Ejemplos

**Servidor stdio local (como NotebookLM):**

```json
[
  {
    "label": "notebooklm-local",
    "transport": "stdio",
    "command": ["node", "D:/.mcp/notebooklm-mcp/dist/index.js"]
  }
]
```

**Servidor stdio con variables de entorno:**

```json
[
  {
    "label": "trello-server",
    "transport": "stdio",
    "command": ["D:/.mcp/Scripts/python.exe", "-m", "trello_mcp"],
    "environment": {
      "TRELLO_API_KEY": "tu-api-key",
      "TRELLO_TOKEN": "tu-token"
    }
  }
]
```

**Servidor HTTP/SSE remoto:**

```json
[
  {
    "label": "groq-mcp",
    "transport": "http",
    "server_url": "https://api.groq.com/mcp/server/id",
    "headers": {
      "Authorization": "Bearer tu-token"
    }
  }
]
```

> **Nota**: `model`, `provider`, `temperature`, `top_p`, `context_turns`, `ui_prefs` **NO** están en `mcp.json`. Se gestionan vía endpoints del frontend y se persisten en SQLite (`config_kv`).

---

### 1b. `AGENT.md` — Comportamiento general

`AGENT.md` (si existe en `~/.config/synapseForge/agents/`) se inyecta como sección `## Behavior` en el system prompt de **todos** los agentes (router y sub-agentes), **antes** de `## MANDATORY:`. No reemplaza el system prompt: `system_prompt.md` es siempre la base del router, y cada sub-agente usa su propio `.md`. Sirve para comportamiento general del proyecto (compatibilidad con opencode/claude code).

### 1c. `config.yaml` — Permisos del router

El agente principal (router) no tiene tools ni skills directas por defecto — solo `task`. Si existe `~/.config/synapseForge/config.yaml`, sus permisos se toman de ahí (misma lógica que el frontmatter de los agentes):

```yaml
permissions:
  tool:
    read: allow
  skill:
    mi_skill: allow
  task:
    explorador: allow
```

- Si el archivo **no existe** → el router queda solo con `task`.
- Si existe → usa **solo** los permisos explícitos del yaml.
- `task` está **siempre** disponible: si el yaml no lo lista, se permite para todos los sub-agentes; si lo lista, solo para los indicados.

---

### 2. Configuración runtime (SQLite `config_kv`)

Los siguientes parámetros se seleccionan desde el **frontend** y se guardan en la tabla `config_kv` de SQLite:

| Clave | Descripción | Endpoint |
|-------|-------------|----------|
| `selected_model` | Modelo activo (ej. `qwen/qwen3.6-27b`, `llama3.2:3b`) | `POST /config/models/select` |
| `selected_provider` | Proveedor activo: `LOCAL` (Ollama) o `API` (cualquier provider cloud curado) | `POST /config/models/select` |
| `context_window_turns` | Turnos de historial a mantener (`-1` = todos) | `POST /config/context-window` |
| `decision_enabled` | Habilita el modelo de decisión (`true` / `false`) | `POST /config/models/decision/enabled` |
| `decision_provider` | Proveedor del modelo de decisión | `POST /config/models/decision/select` |
| `decision_model` | Modelo de decisión | `POST /config/models/decision/select` |
| `selected_workflow` | Workflow activo (`smart` = flujo por defecto) | `POST /config/workflows/select` |

Se cargan automáticamente al inicio vía `load_persisted_config()` en `backend/routes/config.py` y se aplican al agente singleton.

> **Modelo por defecto**: no existe. El usuario elige proveedor + modelo y aplica (`POST /config/models/select`). Si hay un modelo persistido de una sesión anterior, se respeta.

#### Flujo de selección en el frontend

1. **Inicio app** → `GET /config/providers` → lista proveedores disponibles (Ollama si `ollama list` responde; cada provider cloud solo si tiene key válida guardada en la DB).
2. Usuario elige proveedor → `GET /config/models?provider=LOCAL|API` → lista modelos de ese proveedor.
3. Usuario elige modelo → `POST /config/models/select` con `{"model": "...", "provider": "LOCAL|API"}` (donde `API` cubre cualquier provider cloud curado).
4. Opcional: `POST /config/context-window` con `{"max_turns": 10}`.

---

## Skills (habilidades del agente)

Las skills se cargan desde el directorio de configuración del usuario:

```
~/.config/synapseForge/skills/
```

En Windows: `%APPDATA%\synapseForge\skills\`

### Estructura de una skill

Cada skill es una subcarpeta con un archivo `SKILL.md`:

```
skills/
├── plumbing-expert/
│   └── SKILL.md
├── electrical-expert/
│   └── SKILL.md
└── welding/
    └── SKILL.md
```

### Formato `SKILL.md`

```markdown
---
description: "Experto en instalaciones de plomería residencial y comercial. Cálculo de caudales, dimensionamiento de tuberías, selección de materiales."
triggers: "plomería, tuberías, caudal, presión, desagüe, agua, sanitarios"
---

# Plomería Experta

## Comportamiento
Cuando el usuario consulte sobre instalaciones de agua, desagües, sanitarios o calefacción por agua, actúa como plomero certificado...

## Reference Guide
### Tablas de referencia
- **Diámetros estándar**: 1/2", 3/4", 1", 1 1/4", 1 1/2", 2"
- **Materiales**: Cobre, PEX, PVC, CPVC, Polipropileno
...
```

### Carga automática

- Al iniciar el loop, `skill_loader.py` escanea `~/.config/synapseForge/skills/`.
- Lee el frontmatter YAML (`description`, `triggers`).
- Filtra según permisos del agente activo (`permissions.py`).
- Inyecta la sección formateada en el system prompt.

### Ejemplo de skill inyectada en el prompt

```
### plumbing-expert
- **Descripción**: Experto en instalaciones de plomería residencial y comercial. Cálculo de caudales, dimensionamiento de tuberías, selección de materiales.
- **Triggers**: plomería, tuberías, caudal, presión, desagüe, agua, sanitarios
```

---

## Tools (herramientas)

El agente distingue tres tipos de herramientas:

### 1. Tools nativas (en `tools.py`)

Definidas como métodos de la clase `Tools`. Incluyen:
- `read`, `write`, `edit`, `glob`, `grep`, `list_dir` — Operaciones de archivos.
- `websearch`, `webfetch` — Búsqueda y fetch web.
- `rag`, `search_memory` — Consulta de colecciones RAG y memoria de largo plazo.
- `check_email`, `send_email` — Correo electrónico (IMAP/SMTP).
- `shell` — Ejecución de comandos en la terminal.
- `skill`, `reference` — Carga de skills y archivos de referencia.
- `help` — Documentación interna de las tools.
- `task` — Delegación a sub-agentes.
- `execute_mcp_tool` — Ejecución de herramientas MCP.

### 2. Tools externas (en `~/.config/synapseForge/tools/`)

Archivos `.py` sueltos que el agente descubre al inicio:

```
tools/
├── mi_herramienta.py
└── otra_herramienta.py
```

Cada tool externa debe cumplir:
- La **primera línea del docstring del módulo** es la descripción que el LLM usa para decidir si invocarla.
- La función principal debe ser `async` y tener el **mismo nombre que el archivo** (sin `.py`).
- Debe devolver el contrato unificado `{status, message, data, usage}`.

**Ejemplo `tools/calculadora.py`:**
```python
"""Realiza operaciones matemáticas básicas."""

async def calculadora(expresion: str) -> dict:
    try:
        resultado = eval(expresion, {"__builtins__": {}}, {})
        return {"status": "success", "data": {"resultado": resultado}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### 3. Tools MCP

Los servidores MCP configurados en `mcp.json` exponen sus herramientas automáticamente. `tools.py` las descubre vía `mcp_helper.py` (usando el SDK oficial `mcp`) y las registra como tools nativas con prefijo `mcp_<server>_<tool>`. El agente las invoca igual que cualquier otra tool. Cada servidor tiene un timeout propio: si falla, se aísla y el resto del sistema sigue funcionando.

### Carga y registro

- `tools.py` escanea `~/.config/synapseForge/tools/` al instanciar `Tools`.
- Valida que cada archivo tenga los 4 atributos requeridos.
- Construye el esquema function-calling para el LLM.
- Las tools externas aparecen junto a las nativas y MCP en la lista disponible.

### Ejecución de tools (igual para todos los proveedores)

**El flujo es idéntico para todos los proveedores:**

1. `agent.llm_streaming()` recibe `tools` (lista de esquemas JSON Schema).
2. **Providers OpenAI-compatibles / Google Gemini**: `client.chat.completions.create(tools=..., tool_choice="auto", stream=True)`
3. **Ollama**: `ollama_client.chat(tools=..., stream=True)`
4. Todos los proveedores devuelven `tool_calls` en streaming.
5. `llm_streaming` **normaliza** los tool_calls de todos los formatos a:
   ```python
   {"id": "call_xxx", "name": "tool_name", "args": {"param": "value"}}
   ```
   Y yield `{'type': 'tool_calls_detected', 'content': [normalized_tool_calls]}`.
6. `loop.py` recibe el evento, itera cada `tc` y llama:
   ```python
   result_data = await execute_tool(agent, tc)
   ```
7. `execute_tool` (en `loop_helpers.py`) invoca:
   ```python
   await agent.tools._execute_tool(tc["name"], **tc["args"])
   ```
8. `_execute_tool` en `tools.py` despacha a nativa, externa o MCP — **solo recibe `name` y `**kwargs` (los args del tool_call)**.

> **Los parámetros LLM (`temperature`, `top_p`, `max_tokens`, `model`) se pasan SOLO a `llm_streaming()` — NUNCA a las tools.**

---

## Instalación

1. **Clonar el repositorio**

```bash
>>> git clone https://github.com/<owner>nombre_owner</owner>/<repo>nombre_repo</repo>.git
>>> cd <repo>nombre_repo</repo>
```

2. **Crear y activar un entorno virtual** (recomendado Python 3.11+)

```bash
>>> py -3.11 -m venv .<repo>nombre_repo</repo>
>>> .\.<repo>nombre_repo</repo>\Scripts\Activate.ps1
```

3. **Instalar dependencias**

```bash
>>> pip install -r requirements.txt
```

**Notas:**
- La base de datos SQLite se crea automáticamente en `backend/agent/agent_db/agent.db` al iniciar el agente.
- El directorio de configuración `~/.config/synapseForge/` (skills, tools, agents, mcp.json, config.yaml) se crea automáticamente al arrancar.
- Las variables de entorno se cargan desde `.env` en la raíz del proyecto.
- No requiere servicios externos — SQLite es parte de la stdlib de Python.

---

## Estructura del módulo

```plaintext
backend/agent/
│
├─ __init__.py              # Inicialización del paquete
├─ agent.py                 # Clase principal del agente (LLM provider)
├─ loop.py                  # Bucle while(true) del agente
├─ session.py               # Persistencia SQLite
├─ ddl_setup.py             # Creación idempotente de tablas SQLite
├─ permissions.py           # Resolución de permisos y prompts
├─ tools.py                 # Registro y ejecución de herramientas
├─ agent_db/                # Base de datos SQLite
│   └─ agent.db
├─ prompts/                 # Prompts del sistema
│   ├─ system_prompt.md     # Prompt base del router
│   ├─ help.md              # Documentación interna para tool help
│   ├─ title.md             # Prompt para generar títulos de sesión
│   ├─ mandatory.md         # Reglas ## MANDATORY: inyectadas a todos los agentes
│   ├─ create_skill.md     # Prompt para crear skills con LLM
│   ├─ create_tool.md      # Prompt para crear tools con LLM
│   ├─ create_agent.md     # Prompt para crear agentes con LLM
│   ├─ iterate_skill.md      # Prompt para iterar skills
│   ├─ iterate_tool.md       # Prompt para iterar tools
│   ├─ iterate_agent.md      # Prompt para iterar agentes
│   ├─ interview_workflow.md # Prompt de entrevista para workflows
│   ├─ create_workflow.md    # Prompt para crear workflows con LLM
│   ├─ iterate_workflow.md   # Prompt para iterar workflows
│   ├─ generate_workflow.md  # Prompt para generar el YAML de un workflow
│   ├─ decision_close.md     # Pregunta del modelo de decisión: cierre de paso
│   ├─ decision_continue.md  # Pregunta del modelo de decisión: continuidad del pendiente
│   ├─ evaluate_skills.md    # Prompt para evaluar skills existentes
│   └─ explain_skill.md    # Prompt para explicar skills
├─ utils/                   # Utilidades auxiliares
│   ├─ agent_helpers.py     # Helpers de endpoints AgentInfo
│   ├─ chunking.py          # División de documentos en chunks
│   ├─ clean_memory.py      # Liberación de modelos
│   ├─ config.py            # Configuración vía entorno
│   ├─ config_dir.py        # Gestión del directorio ~/.config/synapseForge/
│   ├─ contract.py          # Contratos de respuesta
│   ├─ create_helpers.py    # Helpers de creación vía LLM
│   ├─ decision.py          # Gates de cierre de paso y continuidad
│   ├─ decision_catalog.py  # Catálogo de modelos de decisión (models.dev)
│   ├─ email_parser.py      # Parseo de correos electrónicos
│   ├─ error_logger.py      # Registro de errores
│   ├─ frontier_helpers.py  # Frontera de tool calls (checkpoints)
│   ├─ loop_helpers.py      # Helpers del loop
│   ├─ mcp_helper.py        # Integración MCP
│   ├─ model_catalog.py     # Catálogo de modelos (models.dev)
│   ├─ model_resolver.py    # Resolución del modelo activo
│   ├─ provider_keys.py     # Gestión de API keys
│   ├─ rag_helpers.py       # Helpers RAG
│   ├─ scheduler_helpers.py # Helpers de tareas programadas
│   ├─ skill_loader.py      # Carga de skills
│   ├─ skills_helpers.py    # Helpers de skills
│   ├─ subagent_logger.py   # Logging de sub-agentes
│   ├─ tools_helpers.py     # Helpers de tools externas
│   ├─ vector_db.py         # Wrapper ChromaDB
│   ├─ workflow_loader.py   # Carga de workflows (<nombre>.yaml)
│   ├─ workflow_runner.py   # Ejecución de workflows
│   ├─ workflow_validator.py # Validación del esquema de workflows
│   └─ workflows_helpers.py # Helpers de workflows (listado, evaluación, referencias)
└─ README.md
```

---

## Flujo principal

El agente sigue un ciclo iterativo:

1. **Inicio**: Se crea o recupera la sesión en SQLite.
2. **Carga**: Se carga el historial de mensajes desde la DB.
3. **Config runtime**: Se cargan `selected_model`, `selected_provider`, `context_window_turns` desde `config_kv`.
4. **Prompt**: Se construye el system prompt (base + skills del agente activo).
5. **Tool resolution**: Se resuelven las herramientas disponibles según permisos (nativas + externas + MCP).
6. **Loop** (`while True`):
   a. Se llama al LLM con `messages` + `tools` vía `agent.llm_streaming()`.
   b. `llm_streaming` normaliza tool_calls de todos los proveedores a `{"id", "name", "args"}` y yield `tool_calls_detected`.
   c. `loop.py` ejecuta cada tool vía `execute_tool(agent, tc)` → `agent.tools._execute_tool(name, **args)`.
   d. Resultados se agregan como `role: "tool"` y continúa el loop.
   e. Si el LLM devuelve contenido sin tool_calls → se emite como `chunk` SSE y se cierra el loop.
7. **Persistencia**: Cada mensaje se guarda en SQLite.
8. **Checkpoints**: Antes de ejecutar cada bloque de tool calls se registran en `step_frontier`; al confirmar cada resultado la fila pasa a `done`. Al iniciar un turno, el trabajo sin confirmar de turnos anteriores se inyecta como mensaje de sistema efímero (si hay modelo de decisión habilitado, `should_keep_pending` decide antes si el mensaje nuevo lo continúa). Al cerrar el paso con respuesta final, `should_close_step` valida el cierre y `clear_turn` borra la frontera del turno.
9. **Eventos SSE**: `chunk`, `tool_call`, `tool_result`, `subagent_call`, `subagent_result`, `session_title`, `decision`, `done`.

---

## Stack Tecnológico

![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003b57?logo=sqlite&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-API-f97316?logo=groq&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google%20Gemini-API-4285F4?logo=google&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-API-8b5cf6?logo=openrouter&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local-000000?logo=ollama&logoColor=white)

---

## Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo [LICENSE](./LICENSE) ubicado en la raíz del repositorio.

---

Copyright (c) 2026 <legal>nombre_legal_empresa</legal>

---