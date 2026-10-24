"""Completion reviewer for the creator flows (tool / skill / agent / workflow).

After the assistant's response, the iterate loop alone cannot tell whether
the work is done: the agent may have only proposed changes and be waiting
for approval (the two-phase flow of the ``iterate_*`` prompts). Emitting the
``*_result_final`` success event unconditionally produces a false "modified
successfully" banner on those turns.

This module answers "did the task finish?" with a separate reviewer call
that runs after the assistant's response, like the chat close gate in
``backend/agent/utils/decision.py``. The reviewer receives the full creator
context — every user/assistant exchange of the conversation — plus the
current artifact content, and judges whether the task is finished:

- When the decision model is ready, it decides with a ``noul`` question
  (``prompts/decision_complete.jinja`` rendered with ``is_llm=False``).
  When the decision call abstains (unavailable or invalid verdict), it
  cascades to the LLM fallback so a transient decision failure does not
  withhold a legitimate success.
- Otherwise an external single-shot LLM call (``llm_process`` with the
  creation model/provider and the same prompt rendered with
  ``is_llm=True``) returns the verdict as JSON.

The verdict is persisted as a ``"decisor"`` message (same role and shape
the chat gates use) under a synthetic ``creator:<kind>:<nombre>`` session
id, so it stays traceable in the ``messages`` table without touching chat
sessions.

Every function manages its own failures and never raises: on any doubt the
creation is NOT complete (fail-closed, so no false success banner is ever
emitted).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.agent.utils.decision import DECISION_CLOSE_THRESHOLD
from backend.agent.utils.error_logger import log_error

_ARTIFACT_MAX_CHARS = 12000
"""Maximum artifact characters sent to the reviewer (the file is proof, not context)."""

_TRANSCRIPT_MAX_CHARS = 12000
"""Maximum transcript characters sent to the reviewer (full exchanges, capped)."""


async def is_creation_complete(
    kind: str,
    nombre: str | None,
    artifact_path: str | Path,
    mensajes: list[dict[str, Any]],
    model: str | None = None,
    provider: str | None = None,
    turn_number: int | None = None,
) -> bool:
    """Decide whether a creator turn actually finished the task.

    Runs after the assistant's response with the full creator context:
    every user/assistant exchange plus the current artifact content. A
    pure question turn whose answer is complete counts as finished.

    Args:
        kind: Creator kind: ``"tool"``, ``"skill"``, ``"agent"`` or ``"workflow"``.
        nombre: Name of the item being created/modified (for traceability).
        artifact_path: File whose content proves what was done.
        mensajes: Full creator context: ``{"role": ..., "content": ...}``
            exchanges between user and assistant.
        model: Creation model for the fallback LLM call.
        provider: Creation provider for the fallback LLM call.
        turn_number: Turn proxy for the persisted ``decisor`` row.

    Returns:
        True only when a reviewer confirms the task is finished. Never raises.
    """
    try:
        from backend.instances import agent

        if agent is None:
            return False
        transcript = _build_transcript(mensajes)
        artifact_text = _read_artifact(artifact_path)
        if artifact_text is None:
            return False
        state: dict[str, Any] = {
            "kind": kind,
            "transcript": transcript,
            "artifact": artifact_text,
        }

        if agent.decision_ready:
            try:
                instructions = agent.prompt("decision_complete", is_llm=False)
            except Exception as exc:
                log_error(str(exc), source="create_review.py:is_creation_complete(prompt)")
                instructions = ""
            if instructions:
                try:
                    questions: dict[str, Any] = {
                        "complete": {"type": "noul", "instructions": instructions}
                    }
                    response = await agent.decision(state, questions)
                    data = (response or {}).get("data") or {}
                    if data.get("available"):
                        answers = data.get("answers") or {}
                        verdict = (answers.get("complete") or {}).get("noul")
                        if isinstance(verdict, (int, float)) and not isinstance(verdict, bool):
                            complete = bool(verdict) and float(verdict) >= DECISION_CLOSE_THRESHOLD
                            _save_reviewer_row(
                                kind, nombre, turn_number, data,
                                (response or {}).get("usage"),
                                float(verdict), complete, reviewer="decision",
                                model=data.get("model"), provider=data.get("provider"),
                            )
                            return complete
                except Exception as exc:
                    log_error(str(exc), source="create_review.py:is_creation_complete(decision)")

        return await _llm_fallback(
            agent, kind, nombre, turn_number, state, model, provider
        )
    except Exception as exc:
        log_error(str(exc), source="create_review.py:is_creation_complete")
        return False


async def _llm_fallback(agent: Any, kind: str, nombre: str | None,
                        turn_number: int | None, state: dict[str, Any],
                        model: str | None, provider: str | None) -> bool:
    """External single-shot LLM verdict used when the decision model is off.

    A fresh call outside the creator's context; the model only sees the
    full user/assistant transcript and the artifact content, and answers
    with a strict JSON verdict.

    Args:
        agent: Agent instance (for ``llm_process`` and ``prompt``).
        kind: Creator kind (for traceability).
        nombre: Item name (for traceability).
        turn_number: Turn proxy for the persisted ``decisor`` row.
        state: Reviewer state (transcript, artifact).
        model: Creation model for the call.
        provider: Creation provider for the call.

    Returns:
        True only when the model answers ``{"complete": true}``. Never raises.
    """
    try:
        if not model or not provider:
            return False
        try:
            instructions = agent.prompt("decision_complete", is_llm=True)
        except Exception as exc:
            log_error(str(exc), source="create_review.py:_llm_fallback(prompt)")
            return False
        state_text = (
            f"## transcript\n{state['transcript']}\n\n"
            f"## artifact\n{state['artifact']}"
        )
        response = await agent.llm_process(
            model=model,
            provider=provider,
            system_content=instructions,
            prompt=state_text,
            response_format="json",
            temperature=0.0,
        )
        data = (response or {}).get("data") if isinstance(response, dict) else None
        verdict_text = data if isinstance(data, str) else ""
        parsed = _extract_json(verdict_text)
        complete = bool(parsed and parsed.get("complete") is True)
        _save_reviewer_row(
            kind, nombre, turn_number, {"model": model, "provider": provider},
            (response or {}).get("usage") if isinstance(response, dict) else None,
            1.0 if complete else 0.0, complete, reviewer="llm",
            model=model, provider=provider,
        )
        return complete
    except Exception as exc:
        log_error(str(exc), source="create_review.py:_llm_fallback")
        return False


def _build_transcript(mensajes: list[dict[str, Any]]) -> str:
    """Render the full creator context as a user/assistant transcript.

    Args:
        mensajes: Creator exchanges (``{"role": ..., "content": ...}``).

    Returns:
        Plain-text transcript, capped. Never raises.
    """
    try:
        lines: list[str] = []
        for msg in mensajes or []:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            speaker = "usuario" if role == "user" else "asistente"
            lines.append(f"### {speaker}\n{content}")
        transcript = "\n\n".join(lines) or "(sin intercambios)"
        if len(transcript) > _TRANSCRIPT_MAX_CHARS:
            transcript = transcript[:_TRANSCRIPT_MAX_CHARS] + "\n…[truncado]"
        return transcript
    except Exception as exc:
        log_error(str(exc), source="create_review.py:_build_transcript")
        return "(sin intercambios)"


def _read_artifact(artifact_path: str | Path) -> str | None:
    """Read the artifact file that proves what was done.

    Args:
        artifact_path: File to read.

    Returns:
        File content (capped), or None when it is missing or empty. Never raises.
    """
    try:
        path = Path(artifact_path)
        if not path.is_file():
            return None
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log_error(str(exc), source="create_review.py:_read_artifact")
            return None
        if not content.strip():
            return None
        if len(content) > _ARTIFACT_MAX_CHARS:
            content = content[:_ARTIFACT_MAX_CHARS] + "\n…[truncado]"
        return content
    except Exception as exc:
        log_error(str(exc), source="create_review.py:_read_artifact")
        return None


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model answer.

    Tries the whole text first (``response_format="json"`` should return
    clean JSON), then a greedy match, then a non-greedy one (safer when
    the reason contains braces).

    Args:
        text: Raw model answer.

    Returns:
        Parsed dict, or None when no JSON object can be read. Never raises.
    """
    try:
        if not text:
            return None
        stripped = text.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        for pattern in (r"\{.*\}", r"\{.*?\}"):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                parsed = json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None
    except Exception:
        return None


def _save_reviewer_row(kind: str, nombre: str | None, turn_number: int | None,
                       data: dict[str, Any], usage: dict[str, Any] | None,
                       verdict: float, complete: bool, reviewer: str,
                       model: str | None, provider: str | None) -> None:
    """Persist the reviewer verdict as a ``"decisor"`` message.

    Same shape the chat gates use (``backend/agent/utils/decision.py``):
    same role, JSON content with question/verdict/threshold/outcome, usage,
    model, provider, turn and step — under a synthetic
    ``creator:<kind>:<nombre>`` session id so it stays traceable in the
    ``messages`` table without touching chat sessions. Never raises.

    Args:
        kind: Creator kind.
        nombre: Item name.
        turn_number: Turn proxy (message count when available).
        data: Decision response data (model, provider).
        usage: Token / time report of the reviewer call.
        verdict: ``noul`` probability (or 1.0/0.0 for the LLM fallback).
        complete: Reviewer outcome — True means the task is finished.
        reviewer: Which reviewer decided (``"decision"`` or ``"llm"``).
        model: Model that decided.
        provider: Provider that decided.
    """
    try:
        from backend.instances import session_manager

        if session_manager is None:
            return
        session_manager.save_message(
            session_id=f"creator:{kind}:{nombre or 'sin-nombre'}",
            role="decisor",
            content=json.dumps({
                "question": "complete",
                "reviewer": reviewer,
                "verdict": verdict,
                "threshold": DECISION_CLOSE_THRESHOLD,
                "completed": complete,
            }),
            status="success",
            usage=usage if isinstance(usage, dict) else None,
            model=model,
            provider=provider,
            turn_number=turn_number,
            step=None,
        )
    except Exception as exc:
        log_error(str(exc), source="create_review.py:_save_reviewer_row")
