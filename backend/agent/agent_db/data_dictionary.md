# Diccionario de datos

Generado por `generate_schema_docs.py` a partir del esquema real (`ddl_setup`). No se edita a mano: se regenera cuando cambia el esquema.

## Tablas

| Tabla | Para qué sirve |
| --- | --- |
| [`sessions`](#sessions) | - |
| [`messages`](#messages) | - |
| [`turn_latency`](#turn_latency) | - |
| [`config_kv`](#config_kv) | - |
| [`providers`](#providers) | - |
| [`provider_api_keys`](#provider_api_keys) | - |
| [`error_log`](#error_log) | - |
| [`context_files`](#context_files) | - |
| [`attachments`](#attachments) | - |
| [`scheduled_tasks`](#scheduled_tasks) | - |
| [`task_runs`](#task_runs) | - |
| [`model_catalog`](#model_catalog) | - |
| [`decision_catalog`](#decision_catalog) | - |
| [`billing`](#billing) | - |
| [`spend`](#spend) | - |
| [`spend_limits`](#spend_limits) | - |
| [`external_usage`](#external_usage) | - |
| [`creator_calls`](#creator_calls) | - |
| [`creator_runs`](#creator_runs) | One row per run of a creator (agent, skill, tool or workflow creator). kind: agent / skill / tool / workflow action: question (asked the user for more information) / create / iterate / exists (the item already existed, nothing was created) status: success / error / aborted item_name: name of the item created or modified, when known. Tokens and cost add up every LLM call the run made. creator_calls keeps the detail of each call; spend is not touched here. |
| [`step_frontier`](#step_frontier) | Frontier of unsettled work units for the current step. One row per dispatched tool call, written at dispatch time (state 'open') and flipped to 'done' when its result commits. Rows are only deleted when the step closes with a validated done signal; a cut flow leaves them behind so the next turn can resume from them. |
| [`message_feedback`](#message_feedback) | Thumbs up / down the user gives to an assistant answer. One row per answer (a turn of a session); clicking again removes it. model and provider are the ones that produced the answer, so feedback can later be read per model. |
| [`workflows`](#workflows) | Registry of workflows. The YAML file stays the definition; the name is the id. A row is created the first time a workflow is saved or run. |
| [`workflow_runs`](#workflow_runs) | One row per workflow execution. status: running / success / error / cancelled source: play (UI button) / tool (called by an agent through the workflow tool) attempt: current attempt, 1..3 (the run resumes from the last committed node). result: final answer of the run. error_text: plain-language failure explanation. Spend of the LLM calls the engine makes by itself (judge, explain, output), not the agent nodes (their cost lives in their child sessions): the tokens/cost columns hold the sum for the run, like a messages row, and usage_calls keeps every call as JSON ([{purpose, provider, model, prompt_tokens, completion_tokens, total_tokens, total_time, cost_input, cost_output, cost_total, created_at}]). spend is NOT touched here: llm_process already contemplates it. |
| [`workflow_run_steps`](#workflow_run_steps) | Commits of a workflow run: one row per node execution. state: open (dispatched) / done (result committed) / failed / stale (a done row invalidated because an earlier step had to be re-run). result holds the complete node output (never truncated) so a retry or a resume after a crash rebuilds the shared state without re-running it. |
| [`notifications`](#notifications) | Notifications of finished workflow runs and scheduled-task executions. Exactly one of workflow_name / task_id is set (FK to the PK of each table). run_id: workflow_runs.id or task_runs.id (as text) to open the detail. status: success / error. read: 0 unread, 1 read. |

## sessions

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |
| `metadata` | TEXT | sí |  |  |
| `title` | TEXT | sí |  |  |
| `parent_id` | TEXT | sí |  | FK → sessions.session_id |

Índices: `idx_sessions_parent_id` (parent_id)

## messages

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  | FK → sessions.session_id |
| `role` | TEXT | no |  |  |
| `content` | TEXT | sí |  |  |
| `reasoning` | TEXT | sí |  |  |
| `tool_calls` | TEXT | sí |  |  |
| `tool_results` | TEXT | sí |  |  |
| `status` | TEXT | sí |  |  |
| `message` | TEXT | sí |  |  |
| `prompt_tokens` | INTEGER | sí |  |  |
| `completion_tokens` | INTEGER | sí |  |  |
| `total_tokens` | INTEGER | sí |  |  |
| `total_time` | REAL | sí |  |  |
| `time_to_first_token` | REAL | sí |  |  |
| `tool_call_id` | TEXT | sí |  |  |
| `tool_name` | TEXT | sí |  |  |
| `model` | TEXT | sí |  |  |
| `provider` | TEXT | sí |  |  |
| `cost_input` | REAL | sí |  |  |
| `cost_output` | REAL | sí |  |  |
| `cost_total` | REAL | sí |  |  |
| `turn_number` | INTEGER | sí |  |  |
| `step` | INTEGER | sí | `0` |  |
| `substep` | INTEGER | sí | `0` |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_messages_session_id` (session_id)

## turn_latency

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  | FK → sessions.session_id |
| `turn_number` | INTEGER | no |  |  |
| `latency` | REAL | sí |  |  |

Índices: `idx_turn_latency_session_turn` (session_id, turn_number)

## config_kv

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `key` | TEXT | no |  | PK |
| `value` | TEXT | sí |  |  |

## providers

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `provider` | TEXT | no |  | PK |
| `label` | TEXT | no |  |  |
| `models` | TEXT | sí |  |  |
| `updated_at` | TEXT | no |  |  |

## provider_api_keys

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `provider` | TEXT | no |  | PK |
| `api_key_encrypted` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

## error_log

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | sí |  |  |
| `parent_id` | TEXT | sí |  |  |
| `turn_number` | INTEGER | sí |  |  |
| `exception` | TEXT | no |  |  |
| `source` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_error_log_created_at` (created_at), `idx_error_log_session_id` (session_id)

## context_files

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `filename` | TEXT | no |  |  |
| `content` | TEXT | no |  |  |
| `created_at` | TEXT | no |  |  |

## attachments

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  | FK → sessions.session_id |
| `turn_number` | INTEGER | no |  |  |
| `file_name` | TEXT | no |  |  |
| `size` | INTEGER | sí |  |  |
| `content` | BLOB | sí |  |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_attachments_session_turn` (session_id, turn_number)

## scheduled_tasks

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | TEXT | no |  | PK |
| `name` | TEXT | no |  |  |
| `prompt` | TEXT | no |  |  |
| `time` | TEXT | no | `'09:00'` |  |
| `days` | TEXT | no | `'[0,1,2,3,4,5,6]'` |  |
| `enabled` | INTEGER | no | `1` |  |
| `repetitions` | TEXT | sí |  |  |
| `tool_permissions` | TEXT | sí |  |  |
| `skill_permissions` | TEXT | sí |  |  |
| `parameters` | TEXT | sí |  |  |
| `last_run_date` | TEXT | sí |  |  |
| `slot_runs` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

## task_runs

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `task_id` | TEXT | no |  | FK → scheduled_tasks.id |
| `session_id` | TEXT | sí |  |  |
| `status` | TEXT | no |  |  |
| `detail` | TEXT | sí |  |  |
| `started_at` | TEXT | no |  |  |
| `finished_at` | TEXT | sí |  |  |

Índices: `idx_task_runs_started_at` (started_at), `idx_task_runs_task_id` (task_id)

## model_catalog

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `provider` | TEXT | no |  |  |
| `model_id` | TEXT | no |  |  |
| `type` | TEXT | sí |  |  |
| `name` | TEXT | sí |  |  |
| `description` | TEXT | sí |  |  |
| `family` | TEXT | sí |  |  |
| `context_window` | INTEGER | sí |  |  |
| `input_limit` | INTEGER | sí |  |  |
| `output_limit` | INTEGER | sí |  |  |
| `reasoning` | INTEGER | sí | `0` |  |
| `reasoning_options` | TEXT | sí |  |  |
| `tool_call` | INTEGER | sí | `0` |  |
| `attachment` | INTEGER | sí | `0` |  |
| `temperature` | INTEGER | sí | `0` |  |
| `structured_output` | INTEGER | sí | `0` |  |
| `modalities_input` | TEXT | sí |  |  |
| `modalities_output` | TEXT | sí |  |  |
| `cost_input` | REAL | sí |  |  |
| `cost_output` | REAL | sí |  |  |
| `cost_cache_read` | REAL | sí |  |  |
| `cost_cache_write` | REAL | sí |  |  |
| `open_weights` | INTEGER | sí | `0` |  |
| `status` | TEXT | sí |  |  |
| `api` | TEXT | sí |  |  |
| `npm` | TEXT | sí |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_model_catalog_context` (context_window), `idx_model_catalog_reasoning` (reasoning), `idx_model_catalog_model` (model_id), `idx_model_catalog_provider` (provider)

## decision_catalog

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `provider` | TEXT | no |  |  |
| `model_id` | TEXT | no |  |  |
| `type` | TEXT | sí |  |  |
| `name` | TEXT | sí |  |  |
| `description` | TEXT | sí |  |  |
| `family` | TEXT | sí |  |  |
| `context_window` | INTEGER | sí |  |  |
| `input_limit` | INTEGER | sí |  |  |
| `output_limit` | INTEGER | sí |  |  |
| `reasoning` | INTEGER | sí | `0` |  |
| `reasoning_options` | TEXT | sí |  |  |
| `tool_call` | INTEGER | sí | `0` |  |
| `attachment` | INTEGER | sí | `0` |  |
| `temperature` | INTEGER | sí | `0` |  |
| `structured_output` | INTEGER | sí | `0` |  |
| `modalities_input` | TEXT | sí |  |  |
| `modalities_output` | TEXT | sí |  |  |
| `cost_input` | REAL | sí |  |  |
| `cost_output` | REAL | sí |  |  |
| `cost_cache_read` | REAL | sí |  |  |
| `cost_cache_write` | REAL | sí |  |  |
| `open_weights` | INTEGER | sí | `0` |  |
| `status` | TEXT | sí |  |  |
| `api` | TEXT | sí |  |  |
| `npm` | TEXT | sí |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_decision_catalog_type` (type), `idx_decision_catalog_model` (model_id), `idx_decision_catalog_provider` (provider)

## billing

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `provider` | TEXT | no |  |  |
| `requests` | INTEGER | sí | `0` |  |
| `prompt_tokens` | INTEGER | sí | `0` |  |
| `completion_tokens` | INTEGER | sí | `0` |  |
| `total_tokens` | INTEGER | sí | `0` |  |
| `cost` | REAL | sí | `0.0` |  |
| `provider_limits` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_billing_provider` (provider)

## spend

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `provider` | TEXT | no |  |  |
| `model` | TEXT | no |  |  |
| `month` | TEXT | no |  |  |
| `requests` | INTEGER | sí | `0` |  |
| `prompt_tokens` | INTEGER | sí | `0` |  |
| `completion_tokens` | INTEGER | sí | `0` |  |
| `total_tokens` | INTEGER | sí | `0` |  |
| `cost_input` | REAL | sí | `0.0` |  |
| `cost_output` | REAL | sí | `0.0` |  |
| `cost_total` | REAL | sí | `0.0` |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_spend_provider_model` (provider, model, month)

## spend_limits

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `provider` | TEXT | no |  |  |
| `model` | TEXT | sí |  |  |
| `limit_amount` | REAL | no |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_spend_limits_provider_model` (provider, model)

## external_usage

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `kind` | TEXT | no |  |  |
| `provider` | TEXT | no |  |  |
| `model` | TEXT | no |  |  |
| `units` | INTEGER | sí | `0` |  |
| `prompt_tokens` | INTEGER | sí | `0` |  |
| `completion_tokens` | INTEGER | sí | `0` |  |
| `duration` | REAL | sí |  |  |
| `session_id` | TEXT | sí |  |  |
| `turn_number` | INTEGER | sí |  |  |
| `step` | INTEGER | sí |  |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_external_usage_kind` (kind)

## creator_calls

(sin descripción)

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `caller` | TEXT | no |  |  |
| `provider` | TEXT | no |  |  |
| `model` | TEXT | no |  |  |
| `prompt_tokens` | INTEGER | sí | `0` |  |
| `completion_tokens` | INTEGER | sí | `0` |  |
| `total_tokens` | INTEGER | sí | `0` |  |
| `total_time` | REAL | sí |  |  |
| `cost_input` | REAL | sí | `0.0` |  |
| `cost_output` | REAL | sí | `0.0` |  |
| `cost_total` | REAL | sí | `0.0` |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_creator_calls_caller` (caller)

## creator_runs

One row per run of a creator (agent, skill, tool or workflow creator). kind: agent | skill | tool | workflow action: question (asked the user for more information) | create | iterate | exists (the item already existed, nothing was created) status: success | error | aborted item_name: name of the item created or modified, when known. Tokens and cost add up every LLM call the run made. creator_calls keeps the detail of each call; spend is not touched here.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `kind` | TEXT | no |  |  |
| `action` | TEXT | sí |  |  |
| `item_name` | TEXT | sí |  |  |
| `description` | TEXT | sí |  |  |
| `status` | TEXT | no | `'success'` |  |
| `provider` | TEXT | sí |  |  |
| `model` | TEXT | sí |  |  |
| `llm_calls` | INTEGER | no | `0` |  |
| `prompt_tokens` | INTEGER | no | `0` |  |
| `completion_tokens` | INTEGER | no | `0` |  |
| `total_tokens` | INTEGER | no | `0` |  |
| `cost_input` | REAL | no | `0.0` |  |
| `cost_output` | REAL | no | `0.0` |  |
| `cost_total` | REAL | no | `0.0` |  |
| `duration` | REAL | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `finished_at` | TEXT | sí |  |  |

Índices: `idx_creator_runs_created_at` (created_at), `idx_creator_runs_kind` (kind)

## step_frontier

Frontier of unsettled work units for the current step. One row per dispatched tool call, written at dispatch time (state 'open') and flipped to 'done' when its result commits. Rows are only deleted when the step closes with a validated done signal; a cut flow leaves them behind so the next turn can resume from them.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  | FK → sessions.session_id |
| `turn_number` | INTEGER | no |  |  |
| `step` | INTEGER | no | `0` |  |
| `substep` | INTEGER | no | `0` |  |
| `tool_call_id` | TEXT | sí |  |  |
| `tool_name` | TEXT | no |  |  |
| `tool_args` | TEXT | sí |  |  |
| `state` | TEXT | no | `'open'` |  |
| `child_id` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_step_frontier_session_turn` (session_id, turn_number)

## message_feedback

Thumbs up / down the user gives to an assistant answer. One row per answer (a turn of a session); clicking again removes it. model and provider are the ones that produced the answer, so feedback can later be read per model.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `session_id` | TEXT | no |  | FK → sessions.session_id |
| `turn_number` | INTEGER | no |  |  |
| `feedback_type` | TEXT | no |  |  |
| `model` | TEXT | sí |  |  |
| `provider` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_message_feedback_created_at` (created_at)

## workflows

Registry of workflows. The YAML file stays the definition; the name is the id. A row is created the first time a workflow is saved or run.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `name` | TEXT | no |  | PK |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

## workflow_runs

One row per workflow execution. status: running | success | error | cancelled source: play (UI button) | tool (called by an agent through the workflow tool) attempt: current attempt, 1..3 (the run resumes from the last committed node). result: final answer of the run. error_text: plain-language failure explanation. Spend of the LLM calls the engine makes by itself (judge, explain, output), not the agent nodes (their cost lives in their child sessions): the tokens/cost columns hold the sum for the run, like a messages row, and usage_calls keeps every call as JSON ([{purpose, provider, model, prompt_tokens, completion_tokens, total_tokens, total_time, cost_input, cost_output, cost_total, created_at}]). spend is NOT touched here: llm_process already contemplates it.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | TEXT | no |  | PK |
| `workflow_name` | TEXT | no |  | FK → workflows.name |
| `session_id` | TEXT | sí |  |  |
| `parent_session_id` | TEXT | sí |  |  |
| `source` | TEXT | no | `'play'` |  |
| `status` | TEXT | no | `'running'` |  |
| `attempt` | INTEGER | no | `1` |  |
| `started_at` | TEXT | no |  |  |
| `finished_at` | TEXT | sí |  |  |
| `result` | TEXT | sí |  |  |
| `error_text` | TEXT | sí |  |  |
| `prompt_tokens` | INTEGER | no | `0` |  |
| `completion_tokens` | INTEGER | no | `0` |  |
| `total_tokens` | INTEGER | no | `0` |  |
| `total_time` | REAL | no | `0` |  |
| `cost_input` | REAL | no | `0` |  |
| `cost_output` | REAL | no | `0` |  |
| `cost_total` | REAL | no | `0` |  |
| `usage_calls` | TEXT | sí |  |  |

Índices: `idx_workflow_runs_started_at` (started_at), `idx_workflow_runs_status` (status), `idx_workflow_runs_name` (workflow_name)

## workflow_run_steps

Commits of a workflow run: one row per node execution. state: open (dispatched) | done (result committed) | failed | stale (a done row invalidated because an earlier step had to be re-run). result holds the complete node output (never truncated) so a retry or a resume after a crash rebuilds the shared state without re-running it.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `run_id` | TEXT | no |  | FK → workflow_runs.id |
| `attempt` | INTEGER | no | `1` |  |
| `step` | INTEGER | no |  |  |
| `substep` | INTEGER | no | `0` |  |
| `node_id` | TEXT | no |  |  |
| `node_type` | TEXT | no |  |  |
| `args` | TEXT | sí |  |  |
| `state` | TEXT | no | `'open'` |  |
| `result` | TEXT | sí |  |  |
| `error` | TEXT | sí |  |  |
| `child_session_id` | TEXT | sí |  |  |
| `created_at` | TEXT | no |  |  |
| `updated_at` | TEXT | no |  |  |

Índices: `idx_workflow_run_steps_run` (run_id, step)

## notifications

Notifications of finished workflow runs and scheduled-task executions. Exactly one of workflow_name / task_id is set (FK to the PK of each table). run_id: workflow_runs.id or task_runs.id (as text) to open the detail. status: success | error. read: 0 unread, 1 read.

| Columna | Tipo | Nulo | Por defecto | Clave |
| --- | --- | --- | --- | --- |
| `id` | INTEGER | no |  | PK |
| `kind` | TEXT | no |  |  |
| `workflow_name` | TEXT | sí |  | FK → workflows.name |
| `task_id` | TEXT | sí |  | FK → scheduled_tasks.id |
| `run_id` | TEXT | sí |  |  |
| `title` | TEXT | no |  |  |
| `status` | TEXT | no |  |  |
| `message` | TEXT | sí |  |  |
| `session_id` | TEXT | sí |  |  |
| `read` | INTEGER | no | `0` |  |
| `created_at` | TEXT | no |  |  |

Índices: `idx_notifications_created_at` (created_at), `idx_notifications_read` (read)
