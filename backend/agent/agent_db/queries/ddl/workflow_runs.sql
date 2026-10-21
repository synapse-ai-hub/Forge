-- Everything a workflow run does, in one table laid out like messages. A run is the group of rows
-- that share run_id (also the id of its session), and kind says what each row is:
--   run: the execution itself (source, status, attempt, started_at, finished_at, result, error_text
--     and its sessions). It is the only row of the run that has a result and a source.
--   node: one execution of a node (step, substep, node_id, node_type, status, result or error_text,
--     child_session_id). The nodes of a step run in parallel, each with its own substep. An agent
--     node adds up the spend of its child session; the other nodes run a tool (tool_name) and
--     their total_time is the seconds they took.
--   decision: verdict of the decision model on the run. status: approved | rejected; result holds
--     the JSON of its answers.
--   judge: verdict of the chat LLM, used when the decision model is not ready. status: approved |
--     rejected | error; result holds the text it answered.
--   output: the LLM call that writes the output of the run (status: success | error).
--   explain: the LLM call that explains in plain language why a run failed (status: success | error).
-- Rows of a run are never deleted when it ends (workflow_run_steps, in contrast, only keeps what is
-- needed to resume a run and is cleaned when it ends well). The spend of a run is the sum of its
-- rows. spend is NOT touched here: llm_process already records it.
-- status of a run row: running | success | error | cancelled. source: play (UI button) | tool
-- (called by an agent through the workflow tool). attempt: attempt that made the row, 1..3.
-- step / substep: step of the workflow and position inside it (node rows); the rows of the engine
-- take the next step of the run, with substep 0. The sessions are kept while they exist; if one is
-- deleted the row stays without it. run_id has no foreign key: it is the group of rows that share
-- it, so no column is unique to reference.
CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id; orders the rows
    run_id TEXT NOT NULL,  -- run the row belongs to; also the id of its session
    workflow_name TEXT NOT NULL,  -- workflow that ran
    kind TEXT NOT NULL,  -- run | node | decision | judge | output | explain
    attempt INTEGER NOT NULL DEFAULT 1,  -- attempt that made the row, 1..3
    step INTEGER NOT NULL DEFAULT 0,  -- step of the workflow (0 in the run row)
    substep INTEGER NOT NULL DEFAULT 0,  -- position of the row inside its step
    node_id TEXT,  -- id of the node in the YAML (node rows)
    node_type TEXT,  -- agent | tool | rag | run (node rows)
    tool_name TEXT,  -- tool a node ran: shell in run nodes, rag in rag nodes, the tool in tool nodes (NULL in agent nodes)
    status TEXT,  -- run: running | success | error | cancelled; node: success | error | cancelled; decision, judge: approved | rejected | error; output, explain: success | error
    source TEXT,  -- play | tool (run row)
    session_id TEXT,  -- session that holds the execution (run row)
    parent_session_id TEXT,  -- session of the agent that called the workflow (run row, source tool)
    child_session_id TEXT,  -- session of the sub-agent (agent node rows)
    result TEXT,  -- output of the run, of the node or of the call
    error_text TEXT,  -- failure message of a node, or plain-language explanation of a failed run
    provider TEXT,  -- provider of the model that produced the row
    model TEXT,  -- model that produced the row
    prompt_tokens INTEGER NOT NULL DEFAULT 0,  -- input tokens
    completion_tokens INTEGER NOT NULL DEFAULT 0,  -- output tokens
    total_tokens INTEGER NOT NULL DEFAULT 0,  -- prompt_tokens + completion_tokens
    total_time REAL NOT NULL DEFAULT 0,  -- seconds the LLM calls took
    cost_input REAL NOT NULL DEFAULT 0,  -- USD cost of the input tokens
    cost_output REAL NOT NULL DEFAULT 0,  -- USD cost of the output tokens
    cost_total REAL NOT NULL DEFAULT 0,  -- cost_input + cost_output
    started_at TEXT NOT NULL,  -- local time the row started
    finished_at TEXT,  -- local time the row ended
    FOREIGN KEY (workflow_name) REFERENCES workflows(name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_run ON workflow_runs(run_id, kind);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_runs_one_run ON workflow_runs(run_id) WHERE kind = 'run';
CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON workflow_runs(workflow_name);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at);
