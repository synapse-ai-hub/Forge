"""Checkpoint tests for synapseForge (real flow, real endpoints, real DB).

Same methodology as ``tests.e2e``: a bot drives the live chat endpoint
(SSE) and asserts on contract structure, never on exact model text. On
top of that, every scenario asserts against the real ``agent.db``
(``step_frontier`` table): what the loop tracked, what a cut flow left
behind, and what the validated close deleted. Nothing is mocked.

Usage::

    python -m tests.checkpoints.runner
    python -m tests.checkpoints.runner --only cut-flow
    python -m tests.checkpoints.runner --base-url http://127.0.0.1:8000

Prerequisites: the backend must run on this same machine (the runner
reads its SQLite file directly) and an LLM must be configured, since the
scenarios need the model to dispatch real parallel tool calls.
"""
