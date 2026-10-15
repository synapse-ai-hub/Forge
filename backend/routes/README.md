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

Documentación de los endpoints HTTP expuestos por `backend/routes`.

### ✨ Rutas documentadas

- **`chat`**: conversación streaming vía Server-Sent Events (SSE).
- **`sessions`**: listado, obtención y eliminación de sesiones de chat.
- **`config`**: gestión de proveedores, modelos, contexto, verbose mode y MCP.
- **`context_files`**: gestión de archivos de contexto (instrucciones y documentos).
- **`metrics`**: métricas de uso, tools, errores y modelos.
- **`rag`**: colecciones RAG, embedding compatibility, reindex, archivos y URLs.
- **`scheduler`**: tareas programadas (agenda) y ejecuciones.
- **`create`**: creación de skills, tools, agents y workflows vía streaming SSE (paquete `backend/routes/create/`: `common.py`, `skill.py`, `tool.py`, `agent.py`, `workflow.py`).
- **`conversation`**: exportación de conversaciones a Markdown.
- **`events`**: event bus SSE (Telegram → frontend).
- **`telegram`**: estado y toggle del bot de Telegram.
- **`agent_items`**: listado y eliminación de skills, tools, agents, MCP y colecciones.
- **`billing`**: métricas de uso, límites de gasto y estadísticas de facturación.

---

## Rutas

### 1. Chat (`backend/routes/chat.py`)

#### `POST /api/chat`

Streaming de un turno de conversación vía Server-Sent Events. Acepta el mensaje del usuario como `FormData`, opcionalmente con archivos adjuntos, y devuelve un `StreamingResponse` con `text/event-stream`.

**Parámetros (FormData):**

- `message` (str, **requerido**): mensaje del usuario.
- `session_id` (str, opcional): id de sesión. Si no se envía, se genera uno (`uuid4`).
- `stream_id` (str, opcional): id de stream.
- `files` (File, opcional): uno o varios archivos adjuntos.

**Respuesta:** `text/event-stream`. Eventos `data: {json}` y un evento final `data: [DONE]`.

---

### 2. Sessions (`backend/routes/sessions.py`)

#### `GET /api/sessions/titles`

Devuelve todos los títulos de sesiones existentes.

**Respuesta:** `JSONResponse` `{status, data: string[]}`.

#### `GET /api/sessions`

Devuelve todas las sesiones de chat ordenadas por actividad más reciente.

**Respuesta:** `JSONResponse` `{status, data: Session[]}` donde `Session` incluye `session_id`, `created_at`, `updated_at`, `title`, `preview`, `message_count`.

#### `GET /api/sessions/{session_id}`

Devuelve el historial completo de mensajes de una sesión.

**Respuesta:** `JSONResponse` `{status, data: {session_id, messages[]}}`.

#### `DELETE /api/sessions/{session_id}`

Elimina una sesión y todos sus mensajes.

**Respuesta:** `JSONResponse` `{status, message}`.

---

### 3. Config (`backend/routes/config.py`)

#### `GET /api/config/providers`

Lista los proveedores disponibles.

**Respuesta:** `JSONResponse` `{status, providers: string[]}`.

#### `GET /api/config/providers/keys`

Lista las API keys guardadas (enmascaradas).

**Respuesta:** `JSONResponse` `{status, data: {provider: masked_key}}`.

#### `PUT /api/config/providers/{provider}/key`

Guarda una API key para un proveedor (cifrada en SQLite).

**Body (JSON):** `{"key": "sk-..."}`.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `DELETE /api/config/providers/{provider}/key`

Elimina la API key de un proveedor.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `GET /api/config/models`

Lista los modelos disponibles según `provider` (query param `provider=LOCAL|API`).

**Respuesta:** `JSONResponse` `{status, provider, models: string[], model: string}`.

#### `POST /api/config/models/select`

Selecciona un modelo para la sesión.

**Body (JSON):** `{"model": "nombre_modelo", "provider": "LOCAL|API"}`.

**Respuesta:** `JSONResponse` `{status, message, model}`.

#### `GET /api/config/parameters`

Devuelve los parámetros de generación configurados (temperature, top_p, etc.).

**Respuesta:** `JSONResponse` `{status, data: {temperature, top_p, max_tokens, ...}}`.

#### `GET /api/config/context-window`

Devuelve el límite de turns de contexto (`-1` = todos).

**Respuesta:** `JSONResponse` `{status, max_turns}`.

#### `POST /api/config/context-window`

Setea el límite de turns de contexto.

**Body (JSON):** `{"max_turns": 10}`.

**Respuesta:** `JSONResponse` `{status, message, max_turns}`.

#### `GET /api/config/verbose-mode`

Devuelve el estado del modo verbose.

**Respuesta:** `JSONResponse` `{status, data: {enabled: bool}}`.

#### `POST /api/config/verbose-mode`

Activa/desactiva el modo verbose.

**Body (JSON):** `{"enabled": true}`.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `GET /api/config/setup-completed`

Indica si el setup inicial fue completado.

**Respuesta:** `JSONResponse` `{status, data: {completed: bool}}`.

#### `POST /api/config/setup-completed`

Marca el setup inicial como completado.

**Body (JSON):** `{"completed": true}`.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `GET /api/config/skills`

Lista las skills disponibles.

**Respuesta:** `JSONResponse` `{status, data: Skill[]}`.

#### `GET /api/config/tools`

Lista las tools disponibles.

**Respuesta:** `JSONResponse` `{status, data: Tool[]}`.

#### `POST /api/config/tools/refresh`

Refresca el listado de tools.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `GET /api/config/agents`

Lista los agentes disponibles.

**Respuesta:** `JSONResponse` `{status, data: Agent[]}`.

#### `GET /api/config/mcp`

Lista los servidores MCP configurados.

**Respuesta:** `JSONResponse` `{status, data: McpServer[]}`.

---

### 4. Context Files (`backend/routes/context_files.py`)

#### `GET /api/context-files`

Lista todos los archivos de contexto subidos.

**Respuesta:** `JSONResponse` `{status, data: ContextFile[]}`.

#### `POST /api/context-files`

Sube un archivo de contexto.

**Parámetros (FormData):**
- `file` (File, **requerido**): archivo a subir.

**Respuesta:** `JSONResponse` `{status, message, data: ContextFile}`.

#### `DELETE /api/context-files/{file_id}`

Elimina un archivo de contexto por ID.

**Respuesta:** `JSONResponse` `{status, message}`.

---

### 5. Metrics (`backend/routes/metrics.py`)

#### `GET /api/metrics/overview`

Métricas agregadas de uso del agente.

**Parámetros (Query):** `days` (int, opcional, default=7).

**Respuesta:** `JSONResponse` `{status, data: MetricsOverview}`.

#### `GET /api/metrics/sessions`

Métricas por sesión.

**Parámetros (Query):** `days` (int, opcional, default=7), `limit` (int, opcional, default=50).

**Respuesta:** `JSONResponse` `{status, data: SessionMetrics[]}`.

#### `GET /api/metrics/tools`

Métricas de uso de tools.

**Parámetros (Query):** `days` (int, opcional, default=7).

**Respuesta:** `JSONResponse` `{status, data: ToolMetrics[]}`.

#### `GET /api/metrics/errors`

Métricas de errores.

**Parámetros (Query):** `days` (int, opcional, default=7).

**Respuesta:** `JSONResponse` `{status, data: ErrorMetrics[]}`.

#### `GET /api/metrics/models`

Métricas de uso por modelo.

**Parámetros (Query):** `days` (int, opcional, default=7).

**Respuesta:** `JSONResponse` `{status, data: ModelMetrics[]}`.

---

### 6. RAG (`backend/routes/rag.py`)

Requiere API key de OpenRouter configurada.

#### `POST /api/rag/collections`

Crea una nueva colección vectorial.

**Body (JSON):** `{"name": "nombre-coleccion", "description": "opcional"}`.

**Respuesta:** `JSONResponse` `{status, message, data: CollectionInfo}`.

#### `GET /api/rag/collections`

Lista todas las colecciones disponibles.

**Respuesta:** `JSONResponse` `{status, data: {collections: CollectionInfo[]}}`.

#### `GET /api/rag/collections/embedding-compatibility`

Clasifica colecciones por compatibilidad de modelo de embeddings.

**Respuesta:** `JSONResponse` `{status, data: {collections: CompatibilityInfo[]}}`.

#### `POST /api/rag/collections/{name}/reindex`

Reindexa una colección con el modelo de embeddings actual.

**Respuesta:** `JSONResponse` `{status, message, data: ReindexReport}`.

#### `DELETE /api/rag/collections/{name}`

Elimina una colección y todos sus datos.

**Respuesta:** `JSONResponse` `{status, message, data: {name}}`.

#### `POST /api/rag/collections/{name}/files`

Sube archivos a una colección: extrae texto, chunk y almacena.

**Parámetros (FormData):** `files` (list[File], **requerido**). Máximo 20 archivos, 50 MB c/u.

**Respuesta:** `JSONResponse` `{status, message, data: {processed[], errors[]}}`.

#### `POST /api/rag/collections/{name}/urls`

Agrega una página web a una colección.

**Body (JSON):** `{"url": "https://..."}`.

**Respuesta:** `JSONResponse` `{status, message, data: {url, chunks}}`.

---

### 7. Scheduler (`backend/routes/scheduler.py`)

#### `GET /api/scheduler/tasks`

Lista todas las tareas programadas ordenadas por horario.

**Respuesta:** `JSONResponse` `{status, tasks: Task[]}`.

#### `POST /api/scheduler/tasks`

Crea una nueva tarea programada.

**Body (JSON):** `{"prompt": "texto", "time": "HH:MM", "days": [0-6]}`.

**Respuesta:** `JSONResponse` `{status, data: Task}`. `400` si falla validación.

#### `PUT /api/scheduler/tasks/{task_id}`

Actualiza una tarea programada.

**Body (JSON):** `{"prompt": "...", "time": "HH:MM", "days": [...], "enabled": true}`. Todos opcionales.

**Respuesta:** `JSONResponse` `{status, data: Task}`. `400` si falla.

#### `DELETE /api/scheduler/tasks/{task_id}`

Elimina una tarea programada y sus ejecuciones registradas.

**Respuesta:** `JSONResponse` `{status, message}`. `404` si no existe.

#### `GET /api/scheduler/runs`

Devuelve las ejecuciones más recientes de tareas (más nuevas primero).

**Respuesta:** `JSONResponse` `{status, runs: Run[]}`.

---

### 8. Create (`backend/routes/create/`)

Creación de skills, tools, agents y workflows vía streaming SSE (mismo patrón que chat). Paquete: `common.py` (router, modelos y helpers), `skill.py`, `tool.py`, `agent.py`, `workflow.py`.

#### `POST /api/create/skill`

Crea una skill con iteración (entrevista + tool calling).

**Body (JSON):** `{"descripcion": "...", "name": "...", "mensajes": [...], "model": "...", "provider": "..."}`.

**Respuesta:** `text/event-stream` con eventos: `chunk`, `tool_call`, `tool_result`, `skill_action`, `skill_result`, `error`, `aborted`.

#### `POST /api/create/tool`

Crea una tool externa vía streaming SSE.

**Body (JSON):** `{"descripcion": "...", "name": "...", "mensajes": [...]}`.

**Respuesta:** `text/event-stream` con eventos: `chunk`, `tool_call`, `tool_result`, `tool_action`, `tool_result_final`, `error`, `aborted`.

#### `POST /api/create/agent`

Crea un agente vía streaming SSE.

**Body (JSON):** `{"descripcion": "...", "name": "...", "mensajes": [...]}`.

**Respuesta:** `text/event-stream` con eventos similares a los anteriores.

#### `POST /api/create/workflow`

Crea un workflow determinista vía streaming SSE (entrevista + validación + aprobación).

**Body (JSON):** `{"descripcion": "...", "name": "...", "mensajes": [...], "model": "...", "provider": "..."}`.

**Respuesta:** `text/event-stream` con eventos: `chunk`, `tool_call`, `tool_result`, `workflow_action`, `workflow_result_final`, `error`, `aborted`.

---

### 9. Conversation (`backend/routes/conversation.py`)

#### `POST /api/conversation/export`

Exporta una conversación a Markdown.

**Body (JSON):** `{"messages": [...], "title": "Conversación"}`.

**Respuesta:** `JSONResponse` `{status, message, data: {markdown: string}}`.

---

### 10. Events (`backend/routes/events.py`)

#### `GET /api/events`

Stream SSE del event bus. El frontend se suscribe para recibir eventos del bot de Telegram y otros sources.

**Respuesta:** `text/event-stream` con eventos del bus.

---

### 11. Telegram (`backend/routes/telegram.py`)

#### `GET /api/telegram/status`

Indica si el bot de Telegram está habilitado.

**Respuesta:** `JSONResponse` `{enabled: bool}`.

#### `POST /api/telegram/toggle`

Activa/desactiva el bot de Telegram.

**Body (JSON):** `{"enabled": true}`.

**Respuesta:** `JSONResponse` `{enabled: bool}`.

#### `GET /api/telegram/active-session`

Devuelve el id de sesión activa compartido entre frontend y Telegram.

**Respuesta:** `JSONResponse` `{session_id: string}`.

#### `POST /api/telegram/active-session`

Setea el id de sesión activa.

**Body (JSON):** `{"session_id": "..."}`.

**Respuesta:** `JSONResponse` `{session_id: string}`.

---

### 12. Agent Items (`backend/routes/agent_items.py`)

#### `GET /api/agent/knowledge`

Lista las colecciones vectoriales disponibles.

**Respuesta:** `JSONResponse` `{status, collections: string[]}`.

#### `DELETE /api/agent/skills/{name}`

Elimina una skill (directorio completo).

**Respuesta:** `JSONResponse` `{status, message}`.

#### `DELETE /api/agent/tools/{name}`

Elimina una tool externa (archivo `.py`).

**Respuesta:** `JSONResponse` `{status, message}`.

#### `DELETE /api/agent/agents/{name}`

Elimina un agente (archivo `.md`).

**Respuesta:** `JSONResponse` `{status, message}`.

#### `DELETE /api/agent/mcp/{label}`

Elimina un servidor MCP de la configuración.

**Respuesta:** `JSONResponse` `{status, message}`.

#### `DELETE /api/agent/knowledge/{collection}`

Elimina una colección vectorial.

**Respuesta:** `JSONResponse` `{status, message}`.

---

### 13. Billing (`backend/routes/billing.py`)

Gestión de gasto y límites de presupuesto por proveedor y modelo.

#### `GET /api/usage-metrics`

Devuelve métricas de uso agregadas por proveedor-modelo.

**Parámetros (Query):** `provider` (str, opcional) — filtra por proveedor.

**Respuesta:** `JSONResponse` `{status, data: {by_provider[], totals}}` con `prompt_tokens`, `completion_tokens`, `total_tokens` y `cost` por proveedor.

#### `GET /api/billing-config`

Devuelve los límites de gasto configurados.

**Parámetros (Query):** `provider` (str, opcional), `model` (str, opcional).

**Respuesta:** `JSONResponse` `{status, data: {limits[], count}}`.

#### `POST /api/billing-config`

Configura un límite de gasto para un proveedor o proveedor-modelo.

**Parámetros (Query):** `provider` (str, **requerido**), `model` (str, opcional), `limit_amount` (float, **requerido**, >= 0). Usar `0` para eliminar el límite.

**Respuesta:** `JSONResponse` `{status, message, data}`.

#### `GET /api/billing-stats`

Devuelve estadísticas de facturación con totales por proveedor.

**Parámetros (Query):** `provider` (str, opcional).

**Respuesta:** `JSONResponse` `{status, data: {by_provider[], totals}}` con `current_spend` por proveedor.

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
