"""Early exits of ``AgentLoop.run`` finish cleanly.

``run()`` has a ``finally`` block that reads the title task, which only exists
from step 5b on. Any exit before that (depth guard, session error, a message
blocked by the guardrail) used to raise ``UnboundLocalError`` there instead of
returning. This runs the real ``run()`` through its first early exit, the depth
guard, which needs no database and no LLM.
"""

from __future__ import annotations

import asyncio

from backend.agent.loop import AgentLoop
from backend.agent.loop import agent_loop as agent_loop_module
from backend.agent.loop.constants import MAX_SUBAGENT_DEPTH
from backend.instances import agent, session_manager


def test_exit_before_the_title_step_ends_the_stream_without_error(monkeypatch):
    # log_error writes to the real error_log table; keep this test off agent.db
    monkeypatch.setattr(agent_loop_module, "log_error", lambda *_a, **_k: None)

    async def collect():
        loop = AgentLoop(agent=agent, session_manager=session_manager)
        return [
            event
            async for event in loop.run(
                session_id="early-exit", user_message="hola", depth=MAX_SUBAGENT_DEPTH
            )
        ]

    events = asyncio.run(collect())
    assert "profundidad máxima" in events[0]
    assert events[-1] == "data: [DONE]\n\n"
