-- Everything the creators (agent, skill, tool and workflow) do, in one table laid out like
-- messages. One creator conversation (creator_id) is a chain of rows:
--   user: what the user wrote in a request (the first one carries setup, the JSON of the form).
--   assistant: text and reasoning the creator streamed.
--   tool: a tool call of the creator with its arguments (tool_calls) and result (tool_results).
--   result: how the request ended (action, item_name, status, message, seconds in total_time).
--   call: one LLM call with its tokens and cost. Calls of the evaluators
--     have no conversation (creator_id NULL). spend is not touched here: llm_process
--     already records it. The usage of a request lives in its call rows.
-- The conversations of a creator are listed in its history sidebar and can be reopened to keep
-- modifying what was created. creator_id has no foreign key: no table holds the conversations,
-- they are the group of rows that share it. The provider is free text (it can be unknown).
CREATE TABLE IF NOT EXISTS creators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id; orders the rows
    creator_id TEXT,  -- conversation the row belongs to (NULL for calls outside a conversation)
    kind TEXT NOT NULL,  -- agent | skill | tool | workflow | other
    role TEXT NOT NULL,  -- user | assistant | tool | result | call
    content TEXT,  -- text of a user or assistant row
    reasoning TEXT,  -- reasoning streamed by the creator
    tool_calls TEXT,  -- JSON with the arguments of the tool call (tool rows)
    tool_results TEXT,  -- JSON with the result of the tool call (tool rows)
    tool_name TEXT,  -- tool the creator called (tool rows)
    status TEXT,  -- success | error | aborted (result rows)
    message TEXT,  -- result or failure message shown to the user (result rows)
    caller TEXT,  -- who made the LLM call, e.g. creator:skill:generate (call rows)
    action TEXT,  -- question | create | iterate | exists (result rows)
    item_name TEXT,  -- name of the item created or modified (result rows)
    setup TEXT,  -- JSON with the form of the request: description, name, parameters, ... (first user row)
    provider TEXT,  -- provider used
    model TEXT,  -- model used
    prompt_tokens INTEGER DEFAULT 0,  -- input tokens (call rows)
    completion_tokens INTEGER DEFAULT 0,  -- output tokens (call rows)
    total_tokens INTEGER DEFAULT 0,  -- input + output tokens (call rows)
    total_time REAL,  -- seconds the call or the request took
    time_to_first_token REAL,  -- seconds until the first token arrived (assistant rows)
    cost_input REAL DEFAULT 0.0,  -- USD cost of the input tokens
    cost_output REAL DEFAULT 0.0,  -- USD cost of the output tokens
    cost_total REAL DEFAULT 0.0,  -- cost_input + cost_output
    turn_number INTEGER,  -- turn of the conversation (1, 2, ...); NULL in old rows
    step INTEGER,  -- step inside the turn (one per LLM round); NULL in old rows
    substep INTEGER,  -- position inside the step (parallel tool calls); NULL in old rows
    tool_call_id TEXT,  -- id of the tool call, in tool rows (links to the assistant row)
    created_at TEXT NOT NULL  -- local time, ISO format
);

CREATE INDEX IF NOT EXISTS idx_creators_creator_id ON creators(creator_id);
CREATE INDEX IF NOT EXISTS idx_creators_kind_created_at ON creators(kind, created_at);
CREATE INDEX IF NOT EXISTS idx_creators_caller ON creators(caller);
