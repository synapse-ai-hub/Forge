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

El módulo **Agent** es el núcleo del asistente conversacional. Implementa un bucle `while(true)` que itera con el LLM usando detección nativa de tool calls, ejecuta las herramientas, persiste cada mensaje en SQLite y acota el contexto del historial por turnos. Soporta proveedores cloud curados (OpenAI-compatibles y Google Gemini) y local (Ollama).

### ✨ Características Principales

- **Loop iterativo nativo**: Llama al LLM en un `while(true)` — si responde con `tool_calls`, las ejecuta y continúa; si responde con contenido, lo entrega y termina.
- **Persistencia SQLite**: Cada mensaje, tool call y resultado se guarda automáticamente en `agent_db/agent.db`.
- **Contexto acotado**: El historial enviado al LLM se limita a los últimos N turnos (`context_window_turns`), con un medidor del uso de la ventana del modelo.
- **Soporte multi-proveedor**: Funciona con proveedores cloud curados (OpenAI-compatibles y Google Gemini) y Ollama (local) sin cambiar la lógica del loop.
- **Permisos y prompts**: Resolución dinámica de herramientas y skills desde archivos markdown de agente. Los prompts del sistema son templates Jinja que se adaptan a las tools habilitadas.
- **Integración MCP**: Servidores MCP por stdio, HTTP o SSE definidos en `mcp.json` (`~/.config/synapseForge/`), con interruptor para activarlos o desactivarlos.
- **Checkpoints de flujo**: Cada tool call despachada se registra en `step_frontier`; si el flujo se corta, el trabajo sin confirmar se retoma en el turno siguiente.
- **Modelo de decisión opcional**: Un modelo de decisión (System One) valida el cierre de cada paso y la continuidad del trabajo pendiente, y revisa el mensaje del usuario como guardrail de seguridad. Deshabilitado, el flujo no hace ninguna llamada extra.
- **Reglas de seguridad**: Reglas contra prompt injection, fuga de datos y comandos o SQL peligrosos. Van en el system prompt del router o, con el modelo de decisión habilitado, las evalúa el decisor.
- **Workflows deterministas**: Flujos en YAML que se ejecutan con un botón play, en segundo plano. Cada ejecución se guarda en su propia tabla, se reintenta hasta 3 veces retomando desde el último nodo confirmado y avisa el resultado con una notificación. Los agentes también pueden ejecutarlos con la tool `workflow`.

---

## ¿Qué resuelve?

- **Persistencia de conversaciones**: No pierde el historial entre sesiones — todo queda en SQLite.
- **Ejecución autónoma de herramientas**: El agente decide qué herramientas usar según la conversación, sin intervención manual.
- **Contexto ajustable**: Evita sobrecargar el LLM con historial innecesario mediante un límite de turnos configurable.
- **Separación de responsabilidades**: Cada módulo (loop, sesión, contexto, configuración, permisos) tiene una función específica y desacoplada.
- **Configuración MCP persistente**: Servidores MCP se guardan en `mcp.json` y sobreviven a reinicios.
- **Modelo/Proveedor/Contexto persistidos en SQLite**: Selección de modelo, proveedor y ventana de contexto se guardan en la tabla `config_kv` y se restauran al arrancar.

---

## Estructura del producto

### 1. `loop/` — Bucle principal del agente

Implementa el `while(true)` orquestador. Por cada mensaje del usuario:
1. Resuelve el modelo y los parámetros (override global → frontmatter del agente → valores por defecto).
2. Crea o recupera la sesión en SQLite y calcula el número de turno.
3. Resuelve las herramientas del agente según sus permisos, antes de armar el prompt porque el prompt del router depende de ellas.
4. Construye el system prompt: base, contexto, `AGENT.md`, `MANDATORY`, seguridad, fecha, skills y directorio temporal.
5. Carga el historial (últimos N turnos) y arma los mensajes.
6. Con un modelo de decisión habilitado, revisa el mensaje del usuario (solo el router); si lo bloquea, responde sin llamar al LLM.
7. Guarda el mensaje del usuario y retoma o descarta el trabajo pendiente de turnos anteriores.
8. En el primer turno de una sesión raíz genera el título en segundo plano.
9. Itera hasta `MAX_ITERATIONS` (25): llama al LLM en streaming → si hay `tool_calls` las ejecuta (las de una misma respuesta, en paralelo) y continúa → si hay contenido lo emite como SSE y termina. Reintenta las respuestas vacías (hasta 2) y los errores transitorios o de rate limit del proveedor con backoff exponencial (hasta 5).
10. Persiste cada mensaje en SQLite y, al cerrar el turno de una sesión raíz, lo indexa en la memoria de largo plazo.

Expone el método `run(session_id, user_message, ...)` que retorna un `AsyncGenerator` de eventos SSE: `turn`, `chunk`, `reasoning`, `tool_call`, `tool_result`, `subagent_call`, `subagent_result`, `subagent_event`, `session_title`, `token_counter` y `decision`, seguidos de `[DONE]`.

El paquete se reparte así: `agent_loop.py` (clase `AgentLoop`), `constants.py` (límites de iteraciones y reintentos), `router_tools.py` (schema de tools de respaldo del router) y `helpers.py` (tipo de API de las tools, permisos del router y overrides de parámetros). `__init__.py` re-exporta `AgentLoop`, así que `from backend.agent.loop import AgentLoop` sigue valiendo.

### 2. `session.py` — Persistencia SQLite

Maneja toda la interacción con la base de datos SQLite:
- Creación y recuperación de sesiones.
- Guardado y carga de mensajes con tool calls y resultados.
- Almacenamiento de configuración clave/valor (`config_kv`): modelo seleccionado, proveedor, ventana de contexto.
- Path de la DB: `backend/agent/agent_db/agent.db` (relativo al project root).

### 3. `utils/config.py` — Configuración del entorno

Dataclasses de configuración del contexto:
- `CompactionConfig`: parámetros de compactación leídos de variables de entorno `AGENT_COMPACTION_*` (`AUTO`, `PRUNE`, `TAIL_TURNS`, `PRESERVE_RECENT_TOKENS`, `RESERVED`, `TRIGGER_THRESHOLD`, `STRATEGY` y `OPTIONS`).
- `SessionContext`: límites de contexto por sesión (`context_limit`, `max_context_tokens`).

El loop no aplica compactación: el historial se acota por turnos (`context_window_turns`).

### 4. `agent.py` y `llm/` — Clase principal del agente

Centraliza la interacción con los proveedores LLM (proveedores cloud curados u Ollama local):
- Selección del proveedor según la configuración persistida en DB (nunca variables de entorno).
- Streaming de respuestas con detección nativa de tool calls.
- Gestión de la instancia de herramientas (`Tools`).
- Atributos runtime: `provider` (`LOCAL` o el id del proveedor cloud), `_resolved_model` (modelo activo), `decision_enabled`, `decision_provider` y `decision_model` (modelo de decisión).

`Agent` (en `agent.py`) conserva el estado, los clientes y la limpieza de salida; las llamadas al LLM viven en mixins del paquete `llm/`: `completion.py` (`llm_process`), `streaming.py` (`llm_streaming`), `decision.py` (`decision`), `tool_calls.py` (normalización de tool calls), `gemini.py` (conversión al formato Gemini) y `api_type.py` (resolución del tipo de API del proveedor).

### 5. `tools/` — Registro de herramientas

Paquete que define el catálogo completo de herramientas del agente. `__init__.py` tiene el registro y el despacho centrales (`ToolsBase`) y compone la clase `Tools` con una tool nativa por archivo (`read.py`, `write.py`, `websearch.py`, ...). `from backend.agent.tools import Tools` sigue valiendo.
- Tools nativas, una por archivo.
- Carga dinámica de tools externas desde `~/.config/synapseForge/tools/`.
- Tools de los servidores MCP activos, registradas junto a las demás.
- Construcción del esquema function-calling para el LLM.
- Validación y ejecución de tool calls.

### 6. `permissions.py` — Permisos y prompts de agente

Resuelve en tiempo de ejecución:
- Herramientas permitidas para el agente (`get_tool_permissions`).
- Skills habilitadas (`get_skill_permissions`).
- Contenido del system prompt (`get_agent_prompt`).
- Filtrado de herramientas/skills según el agente activo.
- Permisos del agente principal (router) desde la tabla `router_config` (ver `router_config` más abajo).

### 7. `utils/contract.py` — Contratos de respuesta

Define los formatos estándar de respuesta para todas las herramientas del agente:
- `make_success_response` / `make_error_response` para respuestas unificadas.
- Dataclasses `ContractResponse` y `UsageReport` para tipado estricto.
- Validación de estructura de respuesta.

### 8. `utils/` — Utilidades auxiliares

Contiene módulos de soporte genéricos para el funcionamiento del agente:
- `config.py` — Dataclasses de configuración del contexto (`CompactionConfig`, `SessionContext`).
- `config_dir.py` — Gestión del directorio `~/.config/synapseForge/`.
- `contract.py` — Contratos de respuesta.
- `db.py` — Conexiones SQLite a `agent.db`.
- `queries.py` — Carga de los scripts `.sql` de `agent_db/queries/`.
- `clean_memory.py` — Liberación de modelos de GPU/CPU.
- `model_resolver.py` — Resolución y validación del modelo activo.
- `model_catalog.py` — Catálogo de modelos sincronizado desde models.dev.
- `decision_catalog.py` — Catálogo de modelos de decisión sincronizado desde models.dev (`type=decision`).
- `decision.py` — Gates del modelo de decisión: cierre de paso, continuidad del trabajo pendiente y guardrail del mensaje del usuario.
- `frontier_helpers.py` — Registro, resolución y reanudación de la frontera de tool calls.
- `workflow_loader.py`, `workflow_validator.py`, `workflow_runner.py`, `workflows_helpers.py` — Carga, validación, ejecución y helpers de workflows.
- `workflow_service.py`, `workflow_db.py`, `workflow_judge.py` — Ejecuciones de workflows (inicio, reintentos, cancelación, reanudación), su persistencia y el juez/explicador con LLM.
- `notifications_helpers.py` — Notificaciones persistidas de workflows y tareas programadas.
- `creators.py` — Conversaciones de los creadores: envuelve el stream SSE de cada endpoint `/api/create/*`, guarda en `creators` lo que pasa (mensaje del usuario, texto, tool calls y cómo terminó), registra cada llamada de `record_creator_call` bajo su conversación y reconstruye una conversación para reabrirla desde el historial del creador.
- `provider_keys.py` — Gestión de API keys (cifrado Fernet en SQLite).
- `skill_loader.py` — Carga y formateo de skills para el system prompt.
- `skills_helpers.py` — Helpers de evaluación y creación de skills.
- `email_parser.py` — Parseo de correos electrónicos (headers, body, adjuntos).
- `mcp_helper.py` — Integración con MCP (Model Context Protocol): transportes stdio, HTTP y SSE, descubrimiento de tools, health check y activación de servidores.
- `vector_db.py` — Wrapper de ChromaDB (RAG y memoria de largo plazo).
- `rag_helpers.py` — Helpers de RAG (indexación y consulta).
- `chunking.py` — División de documentos en chunks.
- `loop_helpers.py` — Helpers del loop (armado del system prompt, historial y ejecución de tools con verificación de permisos).
- `scheduler_helpers.py` — Agenda: las tareas programadas son workflows cuyo YAML tiene un bloque `schedule` (`enabled` y una lista de `slots` con `time` y `days`). El loop revisa cada 20 segundos qué horarios coinciden con el minuto actual y arranca el workflow con `source = "schedule"` en el mismo motor; también arma la vista de tareas que usan las rutas y Telegram.
- `spend_handler.py` — Registro de gasto y límites de presupuesto por proveedor y modelo.
- `rate_limit_handler.py` — Clasificación de errores de rate limit y mensajes por proveedor.
- `eda_figure.py` — Figuras de distribución de métricas en memoria (base64).
- `create_helpers.py` — Helpers de creación vía LLM (skills, tools, agentes).
- `tools_helpers.py` — Helpers de tools externas.
- `agent_helpers.py` — Helpers de los endpoints AgentInfo.
- `subagent_logger.py` — Logging de sub-agentes.
- `error_logger.py` — Registro de errores en `error_log`.

### 9. `prompts/` — Prompts del sistema

Todos los prompts son templates Jinja (`.jinja`) y se cargan con `agent.prompt(nombre, **contexto)`, que renderiza `prompts/<nombre>.jinja` con las variables que se le pasen. Si el template tiene un error de sintaxis o le falta una variable, se registra el error y se devuelve el texto crudo, sin cortar el chat. Los prompts de los sub-agentes no pasan por acá: se toma el texto del `.md` del agente debajo del frontmatter.

- `system_prompt.jinja` — Prompt base del router. Solo incluye las secciones de las tools que el router tiene habilitadas (`tools`).
- `mandatory.jinja` — Reglas `## MANDATORY:` inyectadas al final del system prompt de todos los agentes.
- `seguridad.jinja` — Reglas de seguridad (prompt injection, fuga de datos, comandos y SQL); las de una tool aparecen solo si el agente la tiene. Sin modelo de decisión se renderiza como `## Seguridad` (reglas e instrucciones) en el system prompt de todos los agentes, después de `MANDATORY`. Con el modelo de decisión habilitado, el router no lo lleva y el decisor recibe las reglas y la pregunta, con el mensaje del usuario como estado.
- `paralelizacion.jinja` — Instrucciones para emitir llamadas independientes en paralelo.
- `title.jinja` — Generación de títulos de sesión.
- `create_*.jinja`, `iterate_*.jinja`, `interview_*.jinja` — Prompts de creación, iteración y entrevista vía LLM (agent, skill, tool, workflow).
- `evaluate_skills.jinja`, `explain_skill.jinja` — Prompts auxiliares. `recursos_creador.jinja` es lo que ven los creadores (todos los agentes, las tools con sus parámetros, las skills y el RAG, y lo que el usuario eligió como obligatorio); `agentes_subagente.jinja` lista los agentes a los que puede delegar un sub-agente. `system_agent_node.jinja` y `user_agent_node.jinja` arman los mensajes de un nodo `agent` de un workflow (el prompt del agente con sus skills, y el prompt del nodo con los resultados de los nodos anteriores).
- `decision_close.jinja`, `decision_continue.jinja` — Instrucciones de las preguntas del modelo de decisión (cierre de paso y continuidad).

Cada template empieza con un comentario Jinja con su nombre, descripción, versión y fecha de actualización; no forma parte del prompt renderizado.

`AGENT.md`, los archivos de contexto y las descripciones de agentes se concatenan como texto plano y nunca se renderizan como template.

### 10. `agent_db/` — Base de datos SQLite

Directorio que contiene el archivo `agent.db` con las tablas:
- `sessions` — Metadatos de cada conversación (las de sub-agentes cuelgan de su sesión padre).
- `messages` — Historial de mensajes con tool calls, resultados y uso de tokens. El rol `decisor` guarda el veredicto del modelo de decisión y nunca se envía al LLM.
- `attachments` — Archivos adjuntos de cada turno.
- `context_files` — Archivos de contexto subidos por el usuario.
- `config_kv` — Configuración persistente (modelo, proveedor, turnos de contexto, modelo de decisión, parámetros).
- `providers` y `provider_api_keys` — Proveedores disponibles y sus API keys cifradas.
- `model_catalog` y `decision_catalog` — Modelos por proveedor (chat y decisión), con límites, modalidades y tarifas.
- `error_log` — Registro de excepciones del backend (session_id, turn_number, exception, source, created_at).
- `step_frontier` — Tool calls despachadas del paso en curso (`open` / `done`).
- `workflows` — Registro de workflows; el nombre es el id y el YAML es la definición.
- `workflow_runs` — Como `messages`: la fila de la corrida (`kind` `run`: estado, intento, resultado, explicación del error y la sesión del agente que la llamó, si la llamó uno), una fila por ejecución de nodo (`node`, con `step` y `substep`; un nodo `agent` suma sus llamadas al LLM), una por cada tool que llama un nodo `agent` (`tool`) y una por llamada del motor (`decision`, `judge` con `approved`/`rejected`, `output`, `explain`), cada una con su resultado, modelo, tokens, tiempo y costo. Un workflow o una tarea programada nunca abre una sesión ni escribe en `messages`.
- `workflow_run_steps` — Commits por nodo (`open`, `done`, `failed`, `stale`) con el resultado completo, para retomar desde el último nodo confirmado. Se borran cuando la corrida termina bien; solo una corrida fallida o cortada los deja.
- `notifications` — Notificaciones de workflows y tareas programadas, con FK al workflow y estado de lectura. «Revisar con el agente» es lo único que abre una sesión: una nueva, con el resultado.
- `message_feedback` — Pulgar arriba o abajo del usuario sobre una respuesta, una fila por `(session_id, turn_number)`. Guarda también el modelo y el proveedor que respondió, y se borra con la sesión.
- `turn_latency` — Latencia de cada turno.
- `spend`, `spend_limits`, `billing` y `external_usage` — Gasto y uso por proveedor y modelo y límites de presupuesto.
- `creators` — Todo lo que hacen los creadores (agente, skill, tool y workflow), con la forma de `messages`: una conversación (`creator_id`) es una cadena de filas `user`, `assistant`, `tool` y `result` (qué hizo, el elemento que creó o modificó y el resultado), más una fila `call` por cada llamada al LLM con sus tokens y gasto. El historial de cada creador reabre las conversaciones para seguir modificando lo creado.

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

Un modelo de decisión (System One, vía `typesafe-sdk`) devuelve respuestas tipadas con confianza en vez de texto. `Agent.decision(state, questions)` acepta preguntas `noul`, `choice` y `score` y devuelve un `ContractResponse` con `data = {available, answers, model, provider}`. Si la sección está deshabilitada, no hay proveedor, modelo o API key, o falta el SDK, no se hace ninguna llamada y `available` es `False`. `Agent.decision_ready` indica si una llamada se haría de verdad.

El modelo se habilita y se elige desde la configuración, de forma independiente al modelo de chat (`config_kv`: `decision_enabled`, `decision_provider`, `decision_model`). Los modelos salen de `decision_catalog`, sincronizado desde `models.dev/api.json?type=decision` como máximo una vez cada 24 horas; mientras no haya sincronización el catálogo está vacío.

Con la sección habilitada hay tres gates, todos de tipo `noul`:

| Gate | Cuándo corre | Qué decide |
|------|--------------|------------|
| `is_message_blocked` | Al iniciar un turno del router | Si el mensaje del usuario intenta violar las reglas de seguridad. Bloquea con confianza `>= 0.8` (`DECISION_GUARD_THRESHOLD`) |
| `should_keep_pending` | Al iniciar un turno con filas `open` | Si el mensaje nuevo continúa el trabajo pendiente. Descarta solo con confianza `<= 0.2` |
| `should_close_step` | El LLM emite una respuesta final sin tool calls | Si la frontera del turno se borra. Cierra si la confianza es `>= 0.8` (`DECISION_CLOSE_THRESHOLD`) |

Los tres fallan abiertos: ante cualquier error o respuesta inválida el mensaje pasa, el paso cierra y el trabajo pendiente se conserva. Cada veredicto se guarda como mensaje de rol `decisor` (`{question, type, verdict, threshold, blocked | kept | closed}`).

**Guardrail.** `is_message_blocked` recibe las reglas de `seguridad.jinja` y el mensaje del usuario (con sus adjuntos) como estado. Si bloquea, el loop emite el evento SSE `decision` con `{"action": "blocked", "reason": "guardrail"}`, responde con un aviso sin llamar al LLM y guarda el mensaje del usuario como `Mensaje bloqueado por el guardrail de seguridad.`, para que no vuelva al contexto en los turnos siguientes. Con el modelo de decisión habilitado, el system prompt del router no incluye las reglas de seguridad. Los sub-agentes las mantienen en su system prompt porque el guardrail revisa solo el mensaje del usuario al router.

**Continuidad.** Al descartar el pendiente, el loop emite el evento SSE `decision` con `{"action": "discarded", "reason": "unrelated"}`.

Sin el modelo habilitado, `should_close_step` acepta la señal del LLM, `should_keep_pending` conserva el pendiente y no hay guardrail de decisión: no hay llamadas extra. Los workflows tienen su propio juez (ver sección Workflows).

### 13. Workflows — `utils/workflow_*.py`

Flujos deterministas definidos en archivos planos `~/.config/synapseForge/workflows/<nombre>.yaml`.

- `workflow_validator.py` — Valida el esquema: `name`, `retries` (0–10), `on_failure` (`continue` | `abort`) y nodos de tipo `agent`, `tool`, `rag` o `run`. Cada nodo tiene `id` y `step`; el workflow tiene exactamente un nodo `final: true`. Un nodo `run` ejecuta `run` (comando de shell), con `timeout` (1000–300000 ms, 30000 por defecto) y `workdir` opcional confinado al directorio del proyecto.
- `workflow_loader.py` — `list_workflows` y `load_workflow` con rechazo de nombres con `..` o separadores de ruta.
- `workflow_runner.py` — `WorkflowRunner.execute_attempt` ejecuta un intento: los pasos en orden, con los nodos del mismo `step` en paralelo con barrera. Cada nodo tiene reintentos con espera exponencial; los de tipo `agent` corren en memoria, sin sesión, con el prompt, los permisos (sin `task`) y los parámetros de su agente; sus llamadas al LLM se suman en la fila del nodo y cada tool que llaman queda como una fila `tool`. Un nodo `run` cuyo comando termina con código distinto de cero falla. Las tools se habilitan con permisos mínimos: solo las que el YAML referencia (`task` nunca se habilita; la delegación se hace con nodos `agent`). Cada nodo se confirma en `workflow_run_steps` con su resultado completo.
- `workflow_service.py` — `WorkflowService` inicia, cancela y reanuda ejecuciones:
  - Una ejecución es una tarea en segundo plano, en paralelo con el chat, el scheduler y otros workflows. Un mismo workflow no puede correr dos veces a la vez.
  - No abre ninguna sesión ni escribe en `messages`: todo queda en `workflow_runs` y los commits en `workflow_run_steps`. Las ejecuciones iniciadas desde una tool guardan la sesión del agente que las llamó (`parent_session_id`).
  - Reintenta hasta 3 intentos en total, con espera exponencial (2 s y 4 s). Cada intento retoma desde el primer nodo sin resultado confirmado; un nodo que estaba en vuelo cuenta como fallido y se vuelve a ejecutar.
  - Al arrancar el backend retoma las ejecuciones que quedaron en `running`; las que llamó un agente se cierran como interrumpidas.
  - Al cancelar, la ejecución queda como `cancelled` y no genera notificación.
- `workflow_judge.py` — Cuando todos los nodos terminan, decide si el workflow terminó bien con los resultados de los nodos: con el modelo de decisión si está listo, o con el modelo de chat si no (un solo prompt, `judge_workflow.jinja`, que según `decision` trae la pregunta o el formato de respuesta y los datos). Si una ejecución falla definitivamente, un LLM redacta una explicación en lenguaje simple (`explain_workflow_error.jinja`); el error técnico va a `error_log`. Cada una de estas llamadas queda como una fila de `workflow_runs`, con su veredicto o texto y su gasto.
- `workflow_db.py` — Persistencia de ejecuciones, commits por nodo y gasto.
- `notifications_helpers.py` — Persiste cada notificación y la empuja a la interfaz por el bus de eventos. Solo notifican las ejecuciones lanzadas con play y las tareas programadas.
- `workflows_helpers.py` — Listado y evaluación de workflows para el creador y `verificar_refs`, que comprueba que existan los agentes, tools y colecciones que el workflow referencia antes de ejecutarlo.

---

## Configuración del usuario

El agente utiliza **dos fuentes de configuración** separadas:

### 1. `mcp.json` — Servidores MCP

```
~/.config/synapseForge/mcp.json
```

En Windows: `%USERPROFILE%\.config\synapseForge\mcp.json`

Este archivo almacena **exclusivamente** la configuración de servidores MCP (Model Context Protocol) como un **array** directo. Se gestiona mediante `backend/agent/utils/config_dir.py` (funciones `load_mcp_servers()` / `save_mcp_servers()`; el guardado es atómico). La conexión se realiza con el SDK oficial `mcp` (`mcp_helper.py`) sobre tres transportes: stdio (proceso local), streamable HTTP y SSE (remotos). El `mcp.json` es la única fuente de verdad: lo que cambia el usuario a mano se aplica al refrescar las tools (botón **Actualizar**) o al reiniciar. Cada servidor tiene timeout propio y health check con un handshake MCP real: si un servidor falla, se aísla y el resto del sistema sigue funcionando.

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
| `transport` | string | `"stdio"` (local), `"http"` (streamable HTTP, remoto) o `"sse"` (remoto). Si falta: `command` implica stdio y una URL implica `http` | inferido |
| `command` | string o list | Comando o lista de comandos para ejecutar | — |
| `args` | list | Argumentos adicionales (solo si command es string) | `[]` |
| `environment` | object | Variables de entorno para el subproceso | `{}` |
| `server_url` | string | URL del servidor HTTP/SSE (también se acepta `url`) | — |
| `headers` | object | Cabeceras HTTP para servidores remotos | `{}` |
| `disabled` | bool | `true` para desactivar sin borrar (no se levanta, no aporta tools y no se ejecuta). También se respeta `enabled: false`. El toggle de la pestaña MCP escribe esta clave | `false` |
| `timeout` | number | Segundos para el handshake y cada llamada | `300` |

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

**Servidor remoto (streamable HTTP; para SSE usar `"transport": "sse"`):**

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

`AGENT.md` (si existe en `~/.config/synapseForge/agents/`) se inyecta como sección `## Behavior` en el system prompt de **todos** los agentes (router y sub-agentes), **antes** de `## MANDATORY:`. No reemplaza el system prompt: `system_prompt.jinja` es siempre la base del router, y cada sub-agente usa su propio `.md`. Sirve para comportamiento general del proyecto (compatibilidad con opencode/claude code).

### 1c. `router_config` — Permisos del router

El agente principal (router) toma sus permisos de la tabla interna `router_config` de la base de datos del sistema (una sola fila con las selecciones de subagentes, tools, skills y colecciones RAG). Se edita únicamente desde la interfaz: panel lateral, pestaña **Router**, con listas desplegables por dimensión (los servidores MCP aparecen en un contenedor con scroll). Misma lógica que el frontmatter de los agentes:

| Dimensión | Qué guarda | Cómo se aplica |
|-----------|-------------|----------------|
| `agentes` | Subagentes a los que puede delegar | `tasks: { agente: allow }` (vía `task`) |
| `tools` | Tools habilitadas | `tools: { tool: allow }` |
| `skills` | Skills inyectadas al system prompt | `skills: { skill: allow }` |
| `rag` | Colecciones RAG consultables | `tools: { rag: { coleccion: allow } }` |

Las skills listadas se inyectan en el system prompt del router como `## Skills Disponibles`, igual que en un sub-agente.

- Si no hay nada guardado → el router usa las tools base (`task`, `search_memory`, `read`, `websearch`, `webfetch`) y no tiene skills.
- Si hay una selección guardada → usa **solo** esos permisos: no se suma ninguna tool base.
- **Piso fijo**: con o sin selección, el router siempre puede usar `rag` sobre las colecciones internas `help` (documentación del sistema, un documento por sección) y `agent_conversations`. Lo que la selección liste en `rag` se suma a esas dos. Las colecciones internas no son para el usuario: no aparecen en las listas de la interfaz.
- `task` solo está disponible si la selección incluye la tool `task` o nombra subagentes; `agentes` limita a qué sub-agentes puede delegar.

El system prompt del router incluye solo las secciones de las tools que tiene habilitadas. Los cambios se aplican en el siguiente mensaje, sin reiniciar el backend.

---

### 2. Configuración runtime (SQLite `config_kv`)

Los siguientes parámetros se seleccionan desde el **frontend** y se guardan en la tabla `config_kv` de SQLite:

| Clave | Descripción | Endpoint |
|-------|-------------|----------|
| `selected_model` | Modelo activo (ej. `qwen/qwen3.6-27b`, `llama3.2:3b`) | `POST /config/models/select` |
| `selected_provider` | Proveedor activo: `LOCAL` (Ollama) o el id de un proveedor cloud curado (`openrouter`, `google`, ...) | `POST /config/models/select` |
| `selected_model_context_window` | Ventana de contexto del modelo activo, en tokens | `POST /config/models/select` |
| `param_temperature`, `param_top_p`, `param_reasoning`, `param_budget_tokens`, `param_response_format` | Parámetros avanzados del modelo (`null` = por defecto) | `POST /config/models/select` |
| `context_window_turns` | Turnos de historial a mantener (`-1` = todos) | `POST /config/context-window` |
| `verbose_mode` | Muestra el detalle de tools y razonamiento en el chat | `POST /config/verbose-mode` |
| `setup_completed` | La pantalla de setup inicial se completó u omitió | `POST /config/setup-completed` |
| `decision_enabled` | Habilita el modelo de decisión (`true` / `false`) | `POST /config/models/decision/enabled` |
| `decision_provider` | Proveedor del modelo de decisión | `POST /config/models/decision/select` |
| `decision_model` | Modelo de decisión | `POST /config/models/decision/select` |
| `telegram_enabled`, `active_session` | Estado del bot de Telegram y sesión activa compartida | `POST /telegram/toggle`, `POST /telegram/active-session` |

Se cargan automáticamente al inicio vía `load_persisted_config()` en `backend/routes/config/runtime.py` y se aplican al agente singleton.

> **Modelo por defecto**: no existe. El usuario elige proveedor + modelo y aplica (`POST /config/models/select`). Si hay un modelo persistido de una sesión anterior, se respeta.

#### Flujo de selección en el frontend

1. **Inicio app** → `GET /config/providers` → lista proveedores disponibles (Ollama si `ollama list` responde; cada provider cloud solo si tiene key válida guardada en la DB).
2. Usuario elige proveedor → `GET /config/models?provider=<id>` (`LOCAL` o el id de un proveedor cloud) → lista modelos de ese proveedor.
3. Usuario elige modelo → `POST /config/models/select` con `{"model": "...", "provider": "<id>"}` y, opcionalmente, los parámetros avanzados.
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

### 1. Tools nativas (en `tools/`)

Definidas como métodos de la clase `Tools`, un módulo por tool. Incluyen:
- `read`, `write`, `edit`, `glob`, `grep`, `list_dir` — Operaciones de archivos.
- `websearch`, `webfetch` — Búsqueda y fetch web.
- `rag`, `search_memory` — Consulta de colecciones RAG y memoria de largo plazo.
- `check_email`, `send_email` — Correo electrónico (IMAP/SMTP).
- `shell` — Ejecución de comandos en la terminal.
- `skill`, `reference` — Carga de skills y archivos de referencia.
- `help` — Documentación interna del agente.
- `query_model_capabilities` — Capacidades de un modelo desde el catálogo local.
- `task` — Delegación a sub-agentes.

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

Los servidores MCP configurados en `mcp.json` exponen sus herramientas automáticamente. `tools/__init__.py` las descubre vía `mcp_helper.py` (usando el SDK oficial `mcp`) y las registra como tools nativas con prefijo `<label>_<tool>` (por ejemplo `notebooklm_ask_question`). Los servidores desactivados (`disabled`) no se descubren. El agente las invoca igual que cualquier otra tool. Cada servidor tiene un timeout propio: si falla, se aísla y el resto del sistema sigue funcionando.

### Carga y registro

- `tools/__init__.py` escanea `~/.config/synapseForge/tools/` al instanciar `Tools`.
- Ignora los archivos que no tengan descripción en el docstring del módulo o una función con el nombre del archivo.
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
6. `loop/agent_loop.py` recibe el evento, itera cada `tc` y llama:
   ```python
   result_data = await execute_tool(agent, tc)
   ```
7. `execute_tool` (en `loop_helpers.py`) vuelve a validar el permiso del agente en ejecución (deny by default) y, si está permitido, invoca:
   ```python
   await agent.tools._execute_tool(tc["name"], **tc["args"])
   ```
8. `_execute_tool` en `tools/__init__.py` despacha a nativa, externa o MCP — **solo recibe `name` y `**kwargs` (los args del tool_call)**.

> **Los parámetros LLM (`temperature`, `top_p`, `max_tokens`, `model`) se pasan SOLO a `llm_streaming()` — NUNCA a las tools.**

---

## Instalación

1. **Clonar el repositorio**

```bash
>>> git clone https://github.com/<owner>nombre_owner</owner>/<repo>nombre_repo</repo>.git
>>> cd <repo>nombre_repo</repo>
```

2. **Crear y activar un entorno virtual** (Python 3.12+)

```bash
>>> py -3.12 -m venv .<repo>nombre_repo</repo>
>>> .\.<repo>nombre_repo</repo>\Scripts\Activate.ps1
```

3. **Instalar dependencias**

```bash
>>> pip install -r requirements.txt
```

**Notas:**
- La base de datos SQLite se crea automáticamente en `backend/agent/agent_db/agent.db` al iniciar el agente.
- El directorio de configuración `~/.config/synapseForge/` (skills, tools, agents, mcp.json) se crea automáticamente al arrancar.
- Las variables de entorno se cargan desde `.env` en la raíz del proyecto (ver la tabla siguiente).
- No requiere servicios externos — SQLite es parte de la stdlib de Python.

### Variables de entorno

Las API keys de los proveedores cloud no se leen del entorno: se guardan cifradas desde la interfaz.

| Variable | Uso | Default |
|----------|-----|---------|
| `MODE` / `VITE_MODE` | Modo `dev` o `prod`; el frontend lo usa para elegir la URL del backend | `dev` |
| `VITE_URL_DEV`, `VITE_URL_PROD` | URL del backend que usa el frontend | `http://localhost:8000` |
| `APP_SECRET_KEY` | Frase para derivar la clave de cifrado de las API keys | clave generada en `~/.config/synapseForge/.secret_key` |
| `XDG_CONFIG_HOME` | Base del directorio de configuración | `~/.config` |
| `CONFIG_BASE_URL` | URL base de la API de configuración que usa el loop | `http://127.0.0.1:8000/api/config` |
| `FRONTIER_TTL_HOURS` | Horas que se conservan las filas `done` de `step_frontier` | `24` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS` | Bot de Telegram y chats autorizados | — |
| `EMAIL_IMAP_SERVER`, `EMAIL_IMAP_PORT`, `EMAIL_SMTP_SERVER`, `EMAIL_SMTP_PORT`, `EMAIL_USER`, `EMAIL_PASS` | Tools `check_email` y `send_email` | puertos `993` y `587` |
| `FILE_UPLOAD_MAX_MB`, `FILE_UPLOAD_OCR_MAX_PAGES`, `FILE_UPLOAD_PDF_TEXT_THRESHOLD`, `FILE_UPLOAD_OCR_DPI` | Extracción de texto de archivos subidos | `50`, `10`, `80`, `200` |
| `AGENT_COMPACTION_*` | Parámetros de `CompactionConfig` | ver `utils/config.py` |

---

## Estructura del módulo

```plaintext
backend/agent/
│
├─ agent.py                 # Clase Agent: estado, clientes y limpieza de salida
├─ llm/                     # Llamadas al LLM por responsabilidad (mixins de Agent)
├─ loop/                    # Bucle while(true) del agente (AgentLoop)
├─ tools/                   # Registro y despacho de tools + una tool nativa por archivo
├─ session.py               # Persistencia SQLite
├─ ddl_setup.py             # Creación idempotente de tablas
├─ permissions.py           # Permisos y prompts por agente
├─ agent_db/                # SQLite: agent.db y queries/ (SQL organizado por tema)
├─ prompts/                 # Prompts del sistema, de creación/iteración y del modelo de decisión (.jinja)
├─ utils/                   # Soporte: contratos, catálogos de modelos, RAG, MCP, workflows,
│                           #   checkpoints (frontier), gasto, etc.
└─ README.md
```

---

## Flujo principal

El agente sigue un ciclo iterativo:

1. **Inicio**: Se resuelven el modelo y los parámetros desde `config_kv`, y se crea o recupera la sesión en SQLite.
2. **Tools**: Se resuelven las herramientas disponibles según permisos (nativas + externas + MCP).
3. **Prompt**: Se construye el system prompt (base del router con las secciones de sus tools, o el `.md` del sub-agente, más contexto, `AGENT.md`, `MANDATORY`, seguridad, skills y fecha).
4. **Historial**: Se carga el historial de los últimos `context_window_turns` turnos.
5. **Guardrail**: Con el modelo de decisión habilitado, se revisa el mensaje del usuario (solo el router); si se bloquea, termina el turno sin llamar al LLM.
6. **Checkpoints**: El trabajo sin confirmar de turnos anteriores se inyecta como mensaje de sistema efímero (si hay modelo de decisión habilitado, `should_keep_pending` decide antes si el mensaje nuevo lo continúa).
7. **Loop** (`while True`, hasta 25 iteraciones):
   a. Se llama al LLM con `messages` + `tools` vía `agent.llm_streaming()`.
   b. `llm_streaming` normaliza tool_calls de todos los proveedores a `{"id", "name", "args"}` y yield `tool_calls_detected`.
   c. `loop/agent_loop.py` ejecuta las tool calls de la respuesta en paralelo vía `execute_tool(agent, tc)` → `agent.tools._execute_tool(name, **args)`. Antes de ejecutar cada bloque se registran en `step_frontier`; al confirmar cada resultado la fila pasa a `done`.
   d. Resultados se agregan como `role: "tool"` y continúa el loop.
   e. Si el LLM devuelve contenido sin tool_calls → se emite como `chunk` SSE; `should_close_step` valida el cierre y `clear_turn` borra la frontera del turno.
8. **Persistencia**: Cada mensaje se guarda en SQLite y el turno de una sesión raíz se indexa en la memoria de largo plazo.
9. **Eventos SSE**: `turn` (número de turno de la respuesta, al inicio; solo el loop raíz), `chunk`, `reasoning`, `tool_call`, `tool_result`, `subagent_call`, `subagent_result`, `subagent_event`, `session_title`, `token_counter`, `decision`, seguidos de `[DONE]`.

---

## Stack Tecnológico

![Python](https://img.shields.io/badge/Python-3.12+-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136+-009688?logo=fastapi&logoColor=white)
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