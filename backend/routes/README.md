<p align="center">
  <img src="../../src/logo_empresa.png" alt="Logo" width="150">
</p>

---

<h1 align="center">[API Routes — <nombre>nombre_proyecto</nombre>]</h1>

---

<p align="center">
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0" />
  </a>
</p>

---

<h3 align="center">[Endpoints HTTP de la API del <nombre>nombre_proyecto</nombre>]</h3>

---

## Descripción

Documentación de los endpoints HTTP expuestos por `backend/main.py` y `backend/routes`. Todos cuelgan de `/api`, salvo `/health`.

Las respuestas siguen dos formatos:

- **Contrato:** `{status, message, data, usage}` (sessions, context files, metrics, RAG, billing, conversation y workflows).
- **Directo:** `{status, ...campos}` o `{status, message}` (config, listados, scheduler, agent items y telegram).

`status` es `"success"` o `"error"`. Los errores de validación de los endpoints directos devuelven además el código HTTP correspondiente.

### ✨ Rutas documentadas

- **`app`**: salud, heartbeat y apagado del servidor.
- **`chat`**: conversación streaming vía Server-Sent Events (SSE).
- **`sessions`**: listado, obtención y eliminación de sesiones de chat.
- **`feedback`**: pulgar arriba o abajo sobre las respuestas del asistente.
- **`config`**: proveedores y API keys, modelos de chat y de decisión, parámetros, ventana de contexto, modo verbose, setup inicial, listados de skills, tools, agentes y MCP, y workflows.
- **`context_files`**: archivos de contexto (instrucciones y documentos).
- **`metrics`**: métricas de sesiones, mensajes, tools, errores, modelos y costos, con exportación a CSV.
- **`rag`**: colecciones RAG, compatibilidad de embeddings, reindexado, archivos y URLs.
- **`scheduler`**: tareas programadas (agenda): listar, editar el horario, eliminar y ver las ejecuciones. Se crean con `POST /api/create/workflow` enviando `schedule`.
- **`workflows`**: listado de workflows con su estado, ejecución con play, cancelación e historial de ejecuciones.
- **`notifications`**: notificaciones persistidas (campanita del header).
- **`create`**: creación de skills, tools, agentes y workflows vía streaming SSE.
- **`conversation`**: exportación de conversaciones a Markdown.
- **`events`**: bus de eventos SSE (Telegram, cambios de configuración, notificaciones y ejecuciones de workflows → frontend).
- **`telegram`**: estado, activación y sesión activa del bot de Telegram.
- **`agent_items`**: borrado de skills, tools, agentes, servidores MCP y colecciones; activación de MCP; esquema y prueba de tools.
- **`billing`**: uso, límites de gasto, estadísticas de facturación y gasto por modelo.

---

## Rutas

### 0. Aplicación (`backend/main.py`)

#### `GET /health`

Estado del servidor. Está fuera de `/api`.

**Respuesta:** `{status: "ok", version, timestamp}`.

#### `POST /api/heartbeat`

Latido que envía el frontend cada 10 segundos. En la aplicación de escritorio, si pasan 3 minutos sin recibir ninguno, el servidor se cierra.

**Respuesta:** `{status: "ok"}`.

#### `POST /api/shutdown`

Apaga el servidor (aplicación de escritorio).

**Respuesta:** `{status: "shutting down"}`.

---

### 1. Chat (`backend/routes/chat.py`)

#### `POST /api/chat`

Streaming de un turno de conversación vía Server-Sent Events. Acepta el mensaje del usuario como `FormData`, opcionalmente con archivos adjuntos, y devuelve un `StreamingResponse` con `text/event-stream`.

**Parámetros (FormData):**

- `message` (str, **requerido**): mensaje del usuario.
- `session_id` (str, opcional): id de sesión. Si no se envía, se genera uno (`uuid4`).
- `stream_id` (str, opcional): id del stream.
- `telegram_chat_id` (str, opcional): chat de Telegram al que se entrega la respuesta final cuando el turno se originó allí.
- `files` (File, opcional): hasta 3 archivos adjuntos, 25 MB en total. El texto se extrae y se agrega al mensaje.

**Respuesta:** `text/event-stream`. Eventos `data: {json}` y un evento final `data: [DONE]`:

| Evento | `content` |
|--------|-----------|
| `turn` | Número de turno de la respuesta, al inicio del stream (solo el loop raíz). |
| `chunk` | Fragmento de texto de la respuesta. |
| `reasoning` | Fragmento del razonamiento del modelo. |
| `tool_call` | `{name, args}` de la tool que se va a ejecutar. |
| `tool_result` | `{name, result}` de la tool ejecutada. |
| `subagent_call` | `{agent_name, prompt}` de la delegación a un sub-agente. |
| `subagent_result` | `{agent_name, result}` del sub-agente. |
| `subagent_event` | Evento interno de un sub-agente, para mostrar su avance. |
| `session_title` | Título generado para la sesión (primer turno). |
| `token_counter` | Uso de la ventana de contexto (`percent`, `context_window`, `prompt_tokens`). |
| `decision` | Acción del modelo de decisión (ver abajo). |

Con un modelo de decisión habilitado, el evento `decision` informa dos casos:

- `{"action": "discarded", "reason": "unrelated"}`: al iniciar el turno se descartó el trabajo pendiente de un turno anterior porque el mensaje nuevo no lo continúa.
- `{"action": "blocked", "reason": "guardrail"}`: el mensaje se bloqueó por las reglas de seguridad y no se llamó al LLM. La respuesta es un `chunk` con el aviso del bloqueo.

---

### 2. Sessions (`backend/routes/sessions.py`)

#### `GET /api/sessions/titles`

Devuelve todos los títulos de sesiones existentes.

**Respuesta:** contrato con `data: string[]`.

#### `GET /api/sessions`

Devuelve las sesiones de chat raíz (sin las de sub-agentes), ordenadas por actividad más reciente.

**Respuesta:** contrato con `data: Session[]`, donde `Session` incluye `session_id`, `title`, `preview`, `created_at`, `updated_at` y `message_count`.

#### `GET /api/sessions/{session_id}`

Devuelve el historial completo de mensajes de una sesión. Cada turno aporta un mensaje del usuario (`id: "msg-<id>"`) y uno del asistente (`id: "turn-<n>"`) con sus bloques (texto, razonamiento y tools) en el orden en que ocurrieron. El mensaje del usuario que bloqueó el guardrail trae `blocked: true` y el texto fijo `Mensaje bloqueado por el guardrail de seguridad.`.

**Respuesta:** contrato con `data: {session_id, messages[], context}`. `context` trae `context_window`, `prompt_tokens`, `total_tokens` y `percent`.

#### `DELETE /api/sessions/{session_id}`

Elimina una sesión y todos sus mensajes.

**Respuesta:** contrato `{status, message}`.

---

### 2b. Feedback (`backend/routes/feedback.py`)

Pulgar arriba o abajo sobre una respuesta del asistente, guardado en `agent.db` (`message_feedback`). Una respuesta se identifica con `(session_id, turn_number)`, el mismo número que trae el mensaje `turn-N` de la historia y el evento SSE `turn` del chat.

#### `GET /api/feedback/{session_id}`

Devuelve el feedback de todas las respuestas de la sesión.

**Respuesta:** `{status, data: {"<turn_number>": "up" | "down"}}`.

#### `PUT /api/feedback/{session_id}/{turn_number}`

Guarda el feedback de una respuesta, o lo cambia si ya tenía. También guarda el modelo y el proveedor que la generaron.

**Body:** `{feedback_type: "up" | "down"}`.

**Respuesta:** `{status, message}`. `status: "error"` si el tipo es inválido, la sesión no existe o el turno no tiene respuesta.

#### `DELETE /api/feedback/{session_id}/{turn_number}`

Quita el feedback de una respuesta (no pasa nada si no tenía).

**Respuesta:** `{status, message}`.

---

### 3. Config (`backend/routes/config/`)

Paquete con un router por tema, armados bajo un único `/config` en `__init__.py`: `runtime.py` (ventana de contexto, modo verbose, setup y `load_persisted_config`), `providers.py`, `parameters.py`, `models.py`, `decision.py` (modelo de decisión), `listings.py` (skills, tools, agentes y MCP) y `workflows.py`.

#### `GET /api/config/providers`

Lista los proveedores disponibles: los que tienen API key guardada y, para Ollama, solo mientras está corriendo.

**Respuesta:** `{status, providers: [{provider, label}]}`.

#### `GET /api/config/providers/keys`

Indica qué proveedores (de chat y de decisión) tienen API key guardada. La key nunca se devuelve.

**Respuesta:** `{status, keys: [{provider, configured}]}`.

#### `PUT /api/config/providers/{provider}/key`

Guarda la API key de un proveedor, cifrada en SQLite. Los proveedores de chat se validan primero contra su API; los de decisión se guardan directamente.

**Body (JSON):** `{"api_key": "sk-..."}`.

**Respuesta:** `{status, message}`. `400` si la key es inválida o el proveedor no existe.

#### `DELETE /api/config/providers/{provider}/key`

Elimina la API key de un proveedor y reconstruye su cliente.

**Respuesta:** `{status, message}`.

#### `GET /api/config/models`

Lista los modelos del proveedor indicado, tomados del catálogo en SQLite.

**Parámetros (Query):** `provider` (str, opcional): `LOCAL` o el id de un proveedor cloud. Sin él se usa el proveedor seleccionado; si no hay ninguno, la lista viene vacía.

**Respuesta:** `{status, provider, provider_label, models: string[], model}`. `model` es el modelo seleccionado o `null`.

#### `POST /api/config/models/select`

Selecciona proveedor y modelo, junto con los parámetros avanzados opcionales. `null` u omitido significa "por defecto". La selección se persiste y emite el evento `model_changed` en el bus de eventos.

**Body (JSON):**

```json
{
  "model": "nombre_modelo",
  "provider": "LOCAL",
  "temperature": 0.7,
  "top_p": 0.9,
  "reasoning": "medium",
  "budget_tokens": 2048,
  "response_format": "json"
}
```

`temperature` va de 0 a 2, `top_p` de 0 a 1 y `response_format` es `text` o `json`. Se valida contra el catálogo que el modelo soporte razonamiento y salida estructurada cuando se piden.

**Respuesta:** `{status, message, model, provider, temperature, top_p, reasoning, budget_tokens, response_format}`. `400` si algún valor es inválido o el modelo no soporta lo pedido.

#### `GET /api/config/models/capabilities`

Devuelve las capacidades de un modelo del catálogo.

**Parámetros (Query):** `model`, `provider` (**requeridos**).

**Respuesta:** `{status, found, reasoning_supported?, reasoning_options?, reasoning_type?, response_format_supported?, temperature_supported?, tool_call_supported?}`. `reasoning_type` es `effort_levels`, `budget_tokens` o `boolean`.

#### `GET /api/config/models/decision`

Lista los proveedores de modelos de decisión (tabla `decision_catalog`, sincronizada desde `models.dev?type=decision`) y la selección actual. El modelo de decisión se elige de forma independiente al modelo de chat.

**Respuesta:** `{status, providers[], provider, model, enabled}`. `provider` y `model` son `null` hasta que se selecciona uno.

#### `POST /api/config/models/decision/select`

Selecciona proveedor y modelo de decisión. El modelo debe existir en el catálogo del proveedor y el proveedor debe tener API key guardada. La selección se persiste en `config_kv` (`decision_provider`, `decision_model`) y solo tiene efecto si la sección está habilitada.

**Body (JSON):** `{"model": "inception/mercury-decide:free", "provider": "openrouter"}`.

**Respuesta:** `{status, message, model, provider}`.

#### `POST /api/config/models/decision/enabled`

Habilita o deshabilita el modelo de decisión (`config_kv`: `decision_enabled`). Deshabilitado, el flujo del agente no hace ninguna llamada de decisión y las reglas de seguridad van en el system prompt del router.

**Body (JSON):** `{"enabled": true}`.

**Respuesta:** `{status, message, enabled}`.

#### `GET /api/config/models/decision/capabilities`

Devuelve la información del catálogo para un modelo de decisión.

**Parámetros (Query):** `model`, `provider` (**requeridos**).

**Respuesta:** `{status, found, context_window?, input_limit?, output_limit?, input_modalities?, output_modalities?, cost_input?, cost_output?}`.

#### `GET /api/config/parameters`

Devuelve los parámetros avanzados persistidos (`null` = por defecto), el modelo y proveedor actuales y si el modelo soporta razonamiento y salida estructurada.

**Respuesta:** `{status, temperature, top_p, reasoning, budget_tokens, response_format, model, provider, reasoning_supported, response_format_supported}`.

#### `GET /api/config/context-window`

Devuelve el límite de turnos de contexto (`-1` = todos) y datos de la ventana del modelo.

**Respuesta:** `{status, max_turns, context_window_tokens, vram_gb, ollama_default_context}`.

#### `POST /api/config/context-window`

Setea el límite de turnos de contexto.

**Body (JSON):** `{"max_turns": 10}`. Acepta `-1` o un entero positivo.

**Respuesta:** `{status, message, max_turns}`.

#### `GET /api/config/verbose-mode`

Devuelve el estado del modo verbose.

**Respuesta:** `{status, verbose_mode}`.

#### `POST /api/config/verbose-mode`

Activa o desactiva el modo verbose.

**Body (JSON):** `{"verbose_mode": true}`.

**Respuesta:** `{status, message, verbose_mode}`.

#### `GET /api/config/setup-completed`

Indica si la pantalla de setup inicial de proveedores se completó u omitió.

**Respuesta:** `{status, completed}`.

#### `POST /api/config/setup-completed`

Marca el setup inicial como completado. No lleva body.

**Respuesta:** `{status, message}`.

#### `GET /api/config/skills`

Lista las skills disponibles.

**Respuesta:** `{status, skills: [{name, description}]}`.

#### `GET /api/config/tools`

Lista las tools disponibles (nativas y externas), sin filtrar por permisos.

**Respuesta:** `{status, tools}`.

#### `POST /api/config/tools/refresh`

Reescanea las tools externas y reconstruye el registry de tools, incluidas las de los servidores MCP activos.

**Respuesta:** `{status, tools, message}`.

#### `GET /api/config/agents`

Lista los agentes disponibles (sin `AGENT.md` ni `ROUTER.md`).

**Respuesta:** `{status, agents}`.

#### `GET /api/config/mcp`

Lista los servidores MCP configurados con su estado (`connected`, `failed` o `disabled`) y el transporte (`stdio`, `http` o `sse`). Cada servidor activo se verifica con un handshake MCP real. `error` viene cargado cuando `mcp.json` no es un array JSON válido.

**Respuesta:** `{status, servers: McpServer[], error: string | null}`. `McpServer` incluye `label`, `status`, `transport` y, si falló, `error`.

#### `GET /api/config/router`

Permisos del agente principal: la selección guardada en la tabla `router_config` más los permisos efectivos que resultan de ella (con el conjunto base y el piso fijo de RAG ya aplicados).

**Respuesta:** `{status, selection, permissions}`.

#### `PUT /api/config/router`

Guarda la selección de permisos del agente principal (`agentes`, `tools`, `skills`, `rag`). Se aplica en el siguiente mensaje, sin reiniciar el backend.

**Body (JSON):** `{"selection": {"agentes": [...], "tools": [...], "skills": [...], "rag": [...]}}`.

**Respuesta:** `{status, message, selection, permissions}`.

#### `GET /api/config/router/selection`

Devuelve solo la selección guardada (vacía si todavía no se guardó nada).

**Respuesta:** `{status, selection}`.

#### `POST /api/config/workflows/validate`

Valida un YAML de workflow sin escribir nada.

**Body (JSON):** `{"yaml": "..."}`.

**Respuesta:** contrato. `200` si es válido, `400` si no.

#### `POST /api/config/workflows/save`

Valida y guarda un workflow como `<nombre>.yaml`. El `name` del YAML debe coincidir con el nombre indicado; el nombre admite minúsculas, números y guiones.

**Body (JSON):** `{"name": "nombre", "yaml": "..."}`.

**Respuesta:** contrato con `data: {name}`.

---

### 4. Context Files (`backend/routes/context_files.py`)

Se montan en `/api/context-files`. Su contenido se inyecta en el system prompt del router y de los sub-agentes.

#### `GET /api/context-files`

Lista los archivos de contexto subidos, del más nuevo al más viejo.

**Respuesta:** contrato con `data: {files: [{id, filename, created_at}]}`.

#### `POST /api/context-files`

Sube un archivo de contexto (máximo 50 MB), extrae su texto y lo guarda en SQLite.

**Parámetros (FormData):** `file` (File, **requerido**).

**Respuesta:** contrato con `data: {id, filename}`.

#### `DELETE /api/context-files/{file_id}`

Elimina un archivo de contexto por id.

**Respuesta:** contrato con `data: {id}`.

---

### 5. Metrics (`backend/routes/metrics.py`)

Todos los endpoints aceptan `time_range` (Query): `1h`, `6h`, `1d`, `1w`, `1m` o `all`. Default `1m`; un valor inválido se trata como `1m`. Los datos se agregan desde `agent.db`.

#### `GET /api/metrics/overview`

Resumen combinado: sesiones, mensajes, errores y tasas de falla, tools más usadas, sesiones por día, tokens, costos y tiempos.

**Respuesta:** contrato con `data: MetricsOverview`.

#### `GET /api/metrics/sessions`

Total de sesiones y gráfico de creación en 12 intervalos.

**Respuesta:** contrato con `data: {total_sessions, cantidad[]}`.

#### `GET /api/metrics/messages`

Las cinco métricas por mensaje: pasos, tokens de entrada, tokens de salida, tiempo y latencia.

**Respuesta:** contrato con `data: {steps[], input_tokens[], output_tokens[], time[], latency[]}`.

#### `GET /api/metrics/tools`

Uso de tools.

**Respuesta:** contrato con `data: {tool_usage[], total_tool_calls, avg_time_per_tool_call, top_subagents[]}`.

#### `GET /api/metrics/errors`

Errores del agente.

**Respuesta:** contrato con `data: {total_errors, errors_by_model[], errors_by_tool[]}`.

#### `GET /api/metrics/models`

Uso por modelo.

**Respuesta:** contrato con `data: {models[], tokens_input[], tokens_output[], tool_calls[], latency_models[], total_model_calls, total_models}`.

#### `GET /api/metrics/costs`

Costos por proveedor y modelo.

**Respuesta:** contrato con `data: {cost_by_model[], total_cost, total_input, total_output}`.

#### `GET /api/metrics/{sessions|messages|tools|models|costs}/export`

Descarga la tabla correspondiente del rango como CSV (un registro por línea).

**Respuesta:** `text/csv` como adjunto.

#### `POST /api/metrics/eda/outliers-image`

Genera la figura de outliers de una métrica con `synapse_tools.eda`. No escribe archivos.

**Body (JSON):** `{"query_file", "value_column", "time_range", "placeholder", "filter_column", "percentile", "model", "provider"}`. Los dos últimos filtran por modelo.

**Respuesta:** contrato con `data: {image, stats}`, donde `image` es PNG en base64.

---

### 6. RAG (`backend/routes/rag.py`)

Se montan en `/api/rag`. Requiere API key de Google configurada (embeddings).

#### `POST /api/rag/collections`

Crea una nueva colección vectorial.

**Body (JSON):** `{"name": "nombre-coleccion", "description": "opcional"}`.

**Respuesta:** contrato con `data: CollectionInfo`.

#### `GET /api/rag/collections`

Lista todas las colecciones disponibles.

**Respuesta:** contrato con `data: {collections: CollectionInfo[]}`.

#### `GET /api/rag/collections/embedding-compatibility`

Clasifica colecciones por compatibilidad de modelo de embeddings.

**Respuesta:** contrato con `data: {collections: CompatibilityInfo[]}`.

#### `POST /api/rag/collections/{name}/reindex`

Reindexa una colección con el modelo de embeddings actual.

**Respuesta:** contrato con `data: ReindexReport`.

#### `DELETE /api/rag/collections/{name}`

Elimina una colección y todos sus datos.

**Respuesta:** contrato con `data: {name}`.

#### `POST /api/rag/collections/{name}/files`

Sube archivos a una colección: extrae texto, lo divide en chunks y lo almacena.

**Parámetros (FormData):** `files` (list[File], **requerido**). Máximo 20 archivos por request, 50 MB cada uno.

**Respuesta:** contrato con `data: {processed[], errors[]}`.

#### `POST /api/rag/collections/{name}/urls`

Agrega una página web a una colección.

**Body (JSON):** `{"url": "https://..."}`.

**Respuesta:** contrato con `data: {url, chunks}`.

---

### 7. Scheduler (`backend/routes/scheduler.py`)

Una tarea programada es un workflow cuyo YAML tiene un bloque `schedule`; su id es el nombre del workflow. Se crea con el creador de workflows (`POST /api/create/workflow` con `schedule`, ver abajo). Corre en el motor de workflows (`source = schedule`) y también se puede ejecutar con play y cancelar como cualquier workflow.

#### `GET /api/scheduler/tasks`

Lista todas las tareas programadas ordenadas por horario.

**Respuesta:** `{status, tasks: Task[]}`. `Task` incluye `id`, `name`, `prompt`, `time`, `days`, `enabled`, `repetitions`, `created_at` y `updated_at`. La tarea es el workflow con bloque `schedule`: `prompt` es su descripción, `time` y `days` son el primer horario y `repetitions` los demás.

#### `PUT /api/scheduler/tasks/{task_id}`

Actualiza el horario de una tarea programada (se reescribe el bloque `schedule` de su YAML). Solo se pueden cambiar `time`, `days`, `repetitions` y `enabled`; el resto se cambia en el workflow.

**Body (JSON):** `time`, `days`, `repetitions` y `enabled`, todos opcionales.

**Respuesta:** `{status, message, task}`. `400` si falla.

#### `DELETE /api/scheduler/tasks/{task_id}`

Elimina una tarea programada: su YAML y sus ejecuciones, commits y notificaciones. No se puede eliminar mientras corre.

**Respuesta:** `{status, message}`. `404` si no existe.

#### `GET /api/scheduler/runs`

Devuelve las ejecuciones más recientes iniciadas por el scheduler, que son las corridas de `workflow_runs` con `source = schedule` (más nuevas primero).

**Respuesta:** `{status, runs: Run[]}`.

---

### 8. Create (`backend/routes/create/`)

Creación de skills, tools, agents y workflows vía streaming SSE (mismo patrón que chat). Paquete: `common.py` (router, modelos y helpers), `skill.py`, `tool.py`, `agent.py`, `workflow.py`.

Todos reciben `descripcion` (**requerida**) y devuelven `text/event-stream`. Las entrevistas llevan el historial en `mensajes` (`[{"role", "content"}]`); `model` y `provider` eligen el modelo para esa creación; `iterate: true` modifica una creación existente en lugar de crear una nueva.

Eventos comunes: `chunk`, `reasoning`, `tool_call`, `tool_result`, `error` y `aborted`.

#### `POST /api/create/skill`

Crea una skill con una entrevista y tool calling.

**Parámetros (FormData):** `descripcion`, `name`, `mensajes` (JSON como string), `model`, `provider`, `iterate` y `files` (archivos cuyo texto se agrega al último mensaje).

**Eventos propios:** `skill_action`, `skill_result`.

#### `POST /api/create/tool`

Crea una tool externa (`.py`).

**Body (JSON):** `{"descripcion", "name", "mensajes", "parametros": [{"name", "type", "description", "required"}], "datos": [...], "model", "provider", "iterate"}`. `datos` lista las variables de entorno o datos externos que usa.

**Eventos propios:** `tool_action`, `tool_result_final`.

#### `POST /api/create/agent`

Crea un agente.

**Body (JSON):** `{"descripcion", "name", "mensajes", "model", "provider", "iterate", "agentes", "tools", "tool_args", "skills", "rag"}`. Los cinco últimos vienen de las tarjetas de permisos: lo que el usuario elige es obligatorio, y el creador ve todo lo que existe y puede sumar otros.

**Eventos propios:** `agent_action`, `agent_result_final`.

#### `POST /api/create/workflow`

Crea un workflow determinista (entrevista, validación y aprobación).

**Body (JSON):** `{"descripcion", "name", "mensajes", "model", "provider", "iterate", "agentes", "tools", "tool_args", "rag", "schedule"}`.

`agentes`, `tools`, `tool_args` (argumentos que el usuario cargó para cada tool elegida) y `rag` vienen de las tarjetas de permisos: lo que el usuario elige es obligatorio, y el creador ve todos los agentes y tools existentes con sus parámetros y puede sumar otros.

Con `schedule` (`{"enabled": true, "slots": [{"time": "09:00", "days": [1, 2]}]}`) crea una tarea programada: es el mismo prompt con la parte de la tarea programada, sin entrevista ni aprobación. `name` es obligatorio, no puede existir ya un workflow con ese nombre y el bloque `schedule` del YAML queda exactamente como se pidió.

**Eventos propios:** `workflow_action`, `workflow_result_final`.

---

### 9. Conversation (`backend/routes/conversation.py`)

#### `POST /api/conversation/export`

Exporta una conversación a Markdown.

**Body (JSON):** `{"messages": [...], "title": "Conversación"}`.

**Respuesta:** contrato con `data: {markdown: string}`.

---

### 10. Events (`backend/routes/events.py`)

#### `GET /api/events`

Stream SSE del bus de eventos. El frontend se suscribe para reaccionar a lo que ocurre fuera de su propio chat. Tipos de evento: `telegram_message`, `telegram_command`, `telegram_create`, `model_changed`, `notification` (una notificación nueva, con su contenido completo) y `workflow_run` (una ejecución cambió de estado: `{run_id, workflow, status, attempt}`).

**Respuesta:** `text/event-stream` con los eventos del bus.

---

### 11. Telegram (`backend/routes/telegram.py`)

#### `GET /api/telegram/status`

Indica si el bot de Telegram está habilitado.

**Respuesta:** `{enabled: bool}`.

#### `POST /api/telegram/toggle`

Activa o desactiva el bot y persiste la elección.

**Body (JSON):** `{"enabled": true}`.

**Respuesta:** `{enabled: bool}`.

#### `GET /api/telegram/active-session`

Devuelve el id de sesión activa compartido entre frontend y Telegram.

**Respuesta:** `{session_id: string}`.

#### `POST /api/telegram/active-session`

Setea el id de sesión activa.

**Body (JSON):** `{"session_id": "..."}`.

**Respuesta:** `{session_id: string}`.

---

### 12. Agent Items (`backend/routes/agent_items.py`)

Se montan en `/api/agent`.

#### `GET /api/agent/knowledge`

Lista las colecciones vectoriales disponibles.

**Respuesta:** `{status, collections: string[]}`.

#### `DELETE /api/agent/skills/{name}`

Elimina una skill (directorio completo).

**Respuesta:** `{status, message}`. `400` si el nombre es inválido, `404` si no existe.

#### `DELETE /api/agent/tools/{name}`

Elimina una tool externa (archivo `.py`).

**Respuesta:** `{status, message}`.

#### `DELETE /api/agent/agents/{name}`

Elimina un agente (archivo `.md`).

**Respuesta:** `{status, message}`.

#### `DELETE /api/agent/mcp/{label}`

Elimina un servidor MCP de `mcp.json`.

**Respuesta:** `{status, message}`.

#### `PUT /api/agent/mcp/{label}/enabled`

Activa o desactiva un servidor MCP. Escribe `disabled` en `mcp.json` y reconstruye el registry de tools, así un servidor desactivado deja de aportar tools de inmediato.

**Body (JSON):** `{"enabled": true}`.

**Respuesta:** `{status, message}`. `400` si falta `enabled`, `404` si el servidor no existe.

#### `DELETE /api/agent/knowledge/{collection}`

Elimina una colección vectorial.

**Respuesta:** `{status, message}`.

#### `GET /api/agent/tools/{tool_name}/schema`

Devuelve la firma de una tool como esquema.

**Respuesta:** `{status, data: {tool, description, properties, required}}`. `404` si la tool no existe.

#### `POST /api/agent/tools/{tool_name}/test`

Ejecuta una tool con los argumentos indicados y devuelve su resultado.

**Body (JSON):** objeto con los argumentos de la tool.

**Respuesta:** `{status, data}`. `404` si la tool no existe, `500` si la ejecución falla.

---

### 13. Billing (`backend/routes/billing.py`)

Gestión de gasto y límites de presupuesto por proveedor y modelo.

#### `GET /api/usage-metrics`

Devuelve métricas de uso agregadas por proveedor-modelo.

**Parámetros (Query):** `provider` (str, opcional) — filtra por proveedor.

**Respuesta:** contrato con `data: {by_provider[], totals}` con `requests`, `prompt_tokens`, `completion_tokens`, `total_tokens` y `cost`.

#### `GET /api/billing-config`

Devuelve los límites de gasto configurados.

**Parámetros (Query):** `provider` (str, opcional), `model` (str, opcional).

**Respuesta:** contrato con `data: {limits[], count}`.

#### `POST /api/billing-config`

Configura un límite de gasto para un proveedor o proveedor-modelo.

**Parámetros (Query):** `provider` (str, **requerido**), `model` (str, opcional), `limit_amount` (float, **requerido**, >= 0). Usar `0` para eliminar el límite.

**Respuesta:** contrato con `data: {provider, model, limit_amount}`.

#### `GET /api/billing-stats`

Devuelve estadísticas de facturación con totales por proveedor.

**Parámetros (Query):** `provider` (str, opcional).

**Respuesta:** contrato con `data: {by_provider[], totals}`, con `current_spend` por proveedor.

#### `GET /api/spend`

Devuelve el gasto registrado por modelo.

**Parámetros (Query):** `provider` (str, opcional).

**Respuesta:** contrato con `data: {spend[], count}`.

---

### 14. Workflows (`backend/routes/workflows.py`)

Ejecución de workflows. El play inicia la ejecución en segundo plano y el resultado llega como notificación. Las ejecuciones corren en paralelo con el chat, el scheduler y otros workflows.

#### `GET /api/workflows`

Lista los workflows con su estado.

**Respuesta:** `{status, workflows: Workflow[]}`. `Workflow` incluye `name`, `description`, `running`, `run_id` (de la ejecución en curso) y `last_run` (última ejecución, o `null`).

#### `POST /api/workflows/{name}/run`

Inicia una ejecución en segundo plano. Verifica antes que existan los agentes, tools y colecciones que el workflow referencia.

**Respuesta:** `{status, message, data: {run_id}}`. La ejecución no abre ninguna sesión. `404` si el workflow no existe, `400` si es inválido o faltan recursos (el mensaje dice qué falta) y `409` si ese workflow ya se está ejecutando.

#### `DELETE /api/workflows/{name}`

Elimina el archivo YAML del workflow y todos sus registros: ejecuciones, commits de nodos, gasto del motor y notificaciones. Las sesiones de sus ejecuciones quedan en el historial. `404` si no existe, `400` si el nombre es inválido y `409` si se está ejecutando.

#### `POST /api/workflows/runs/{run_id}/cancel`

Cancela una ejecución en curso. Queda persistida como `cancelled` y no genera notificación. `404` si la ejecución no está en curso.

#### `GET /api/workflows/runs`

Historial de ejecuciones, de la más reciente a la más antigua.

**Parámetros (Query):** `name` (str, opcional) — filtra por workflow; `limit` (int, por defecto 50, máximo 200).

**Respuesta:** `{status, runs: Run[]}`. `Run` incluye `id`, `workflow_name`, `parent_session_id` (la sesión del agente que la llamó, en `tool`), `source` (`play`, `tool` o `schedule`), `status` (`running`, `success`, `error` o `cancelled`), `attempt`, `started_at`, `finished_at`, `result` y `error_text`.

---

### 15. Notifications (`backend/routes/notifications.py`)

Notificaciones de workflows y tareas programadas. Se guardan hasta que el usuario las elimina.

#### `GET /api/notifications`

**Respuesta:** `{status, notifications: Notification[]}`, de la más reciente a la más antigua. `Notification` incluye `id`, `kind` (`workflow` si se ejecutó con play, `schedule` si la lanzó el scheduler), `workflow_name`, `run_id`, `title`, `status`, `message`, `read` y `created_at`.

#### `POST /api/notifications/read`

Marca todas como leídas (el usuario abrió la campanita).

#### `DELETE /api/notifications/{notification_id}`

Elimina una notificación. `404` si no existe.

#### `DELETE /api/notifications`

Elimina todas las notificaciones.

---

## Pruebas

Servidor corriendo en `http://127.0.0.1:8000` (uvicorn `backend.main:app`).

### `POST /api/chat`

**cURL**
```bash
curl -X POST http://127.0.0.1:8000/api/chat -F "message=Hola, ¿qué podés hacer?"
```

**Invoke (PowerShell)**
```powershell
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/chat" -Method Post -ContentType "application/x-www-form-urlencoded" -Body "message=Hola, ¿qué podés hacer?" -TimeoutSec 120
$resp.Content
```

### `GET /api/sessions`

**cURL**
```bash
curl -X GET http://127.0.0.1:8000/api/sessions
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sessions"
```

### `GET /api/config/providers`

**cURL**
```bash
curl -X GET http://127.0.0.1:8000/api/config/providers
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/providers"
```

### `GET /api/config/models?provider=LOCAL`

**cURL**
```bash
curl -X GET "http://127.0.0.1:8000/api/config/models?provider=LOCAL"
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/models?provider=LOCAL"
```

### `POST /api/config/models/select`

**cURL**
```bash
curl -X POST http://127.0.0.1:8000/api/config/models/select -H "Content-Type: application/json" -d "{\"model\": \"llama3.2\", \"provider\": \"LOCAL\"}"
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/models/select" -Method Post -ContentType "application/json" -Body '{"model": "llama3.2", "provider": "LOCAL"}'
```

### `GET /api/scheduler/tasks`

**cURL**
```bash
curl -X GET http://127.0.0.1:8000/api/scheduler/tasks
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/scheduler/tasks"
```

### `POST /api/rag/collections`

**cURL**
```bash
curl -X POST http://127.0.0.1:8000/api/rag/collections -H "Content-Type: application/json" -d "{\"name\": \"mi-coleccion\", \"description\": \"Test\"}"
```

**Invoke (PowerShell)**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/rag/collections" -Method Post -ContentType "application/json" -Body '{"name": "mi-coleccion", "description": "Test"}'
```

---

## Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo [LICENSE](./LICENSE) ubicado en la raíz del repositorio.

---

Copyright (c) 2026 <legal>nombre_legal_empresa</legal>

---
