"""Persistence of the creator conversations in the ``creators`` table.

A ``CreatorSessionManager`` implements the same surface the agent loop needs
from ``SessionManager`` (``create_session``, ``get_last_turn_number``,
``save_message``, ``load_messages``, ``update_message_tool_results`` and
``save_turn_latency``) but reads and writes ``creators`` instead of
``sessions`` / ``messages``. Creator conversations (``creator_id``) are the
group of rows that share it; there is no row in ``sessions`` for them.

Row layout mirrors ``messages``: ``user`` rows carry the raw message (the
first one also carries the setup form as JSON), ``assistant`` rows carry the
text, reasoning and the requested ``tool_calls``, and ``tool`` rows carry one
call each (linked by ``tool_call_id``) with its result. ``result`` and
``call`` rows keep their historical meaning and are never sent to the LLM.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Any

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.db import DB_PATH
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.queries import load_query
from backend.agent.utils.spend_handler import calculate_cost

logger = logging.getLogger(__name__)


class CreatorSessionManager:
    """Persists creator conversations in the ``creators`` table.

    Same call surface as ``SessionManager`` for the methods the agent loop
    uses, so ``AgentLoop.run`` works unchanged against either store.

    Attributes:
        db_path: Path to the SQLite database file.
        kind: Kind of creator (``agent``, ``skill``, ``tool`` or ``workflow``).
        _lock: Thread lock for write serialisation.
    """

    VALID_ROLES = frozenset({"user", "assistant", "tool", "result", "call", "decisor"})

    def __init__(self, db_path: str = DB_PATH, kind: str = "other") -> None:
        """Initialise the creator session manager.

        Args:
            db_path: Path to the SQLite database file.
            kind: Kind of creator whose conversations this instance stores.
        """
        self.db_path = db_path
        self.kind = kind
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection for each operation.

        Creates the parent directory, opens the connection, sets
        optimised PRAGMAs, and creates tables if they do not exist yet.

        Returns:
            A new ``sqlite3.Connection`` instance.
        """
        import os

        from backend.agent.ddl_setup import setup_database

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        setup_database(conn)
        return conn

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def create_session(
        self, session_id: str, metadata: dict | None = None, parent_id: str | None = None
    ) -> dict:
        """Create a creator conversation (no-op when it already has rows).

        Args:
            session_id: The creator conversation id.
            metadata: Ignored (kept for interface compatibility).
            parent_id: Ignored (creators are never sub-agents).

        Returns:
            A contract response dict indicating success or failure.
        """
        try:
            with self._lock:
                conn = self._get_connection()
                try:
                    existing = conn.execute(
                        load_query("creators/exists.sql"),
                        (session_id,),
                    ).fetchone()
                    if existing is not None:
                        return make_error_response(
                            message=f"Session '{session_id}' already exists.",
                            usage=zero_usage(),
                        )
                    return make_success_response(
                        message="Session created.",
                        data={"session_id": session_id},
                        usage=zero_usage(),
                    )
                finally:
                    conn.close()
        except Exception as e:
            log_error(str(e), source="backend/agent/creator_session.py")
            logger.exception("Failed to create creator session '%s'", session_id)
            return make_error_response(
                message=f"Failed to create creator session '{session_id}'.",
                usage=zero_usage(),
            )

    def has_rows(self, session_id: str) -> bool:
        """Check whether a creator conversation already has stored rows.

        Args:
            session_id: The creator conversation id.

        Returns:
            True when at least one row exists for the conversation.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                load_query("creators/exists.sql"),
                (session_id,),
            ).fetchone()
            return row is not None
        except Exception:
            return False
        finally:
            conn.close()

    def get_last_turn_number(self, session_id: str) -> int:
        """Return the highest turn of a creator conversation.

        Args:
            session_id: The creator conversation id.

        Returns:
            The highest turn number, or 0 when it has no loop-era rows.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                load_query("creators/max_turn.sql"),
                (session_id,),
            ).fetchone()
            if row and row["max_turn"] is not None:
                return int(row["max_turn"])
            return 0
        except Exception as e:
            log_error(str(e), source="backend/agent/creator_session.py")
            logger.exception("Failed to get last turn for '%s'", session_id)
            return 0
        finally:
            conn.close()

    def load_messages(self, session_id: str, max_turns: int = -1) -> list[dict]:
        """Load the rows of a creator conversation in chronological order.

        Only ``user``, ``assistant`` and ``tool`` rows are returned;
        ``result``, ``call`` and ``decisor`` rows are bookkeeping and are
        never sent to the LLM. ``tool_calls`` / ``tool_results`` arrive
        deserialised from JSON (when not null).

        Args:
            session_id: The creator conversation id.
            max_turns: Number of most recent turns to load.
                ``-1`` (default) loads all rows. ``0`` loads only rows
                without a turn (legacy) plus the current incomplete turn.

        Returns:
            List of message dicts. Empty when the conversation does not
            exist or has no rows.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                load_query("creators/load_all.sql"),
                (session_id,),
            ).fetchall()

            if max_turns > 0:
                known_turns = sorted({
                    int(r["turn_number"])
                    for r in rows
                    if r["turn_number"] is not None
                })
                if known_turns:
                    min_turn = max(known_turns[-max_turns], 0)
                    rows = [
                        r for r in rows
                        if r["turn_number"] is None or int(r["turn_number"]) >= min_turn
                    ]

            messages: list[dict] = []
            for row in rows:
                role = row["role"]
                if role not in ("user", "assistant", "tool"):
                    continue
                msg: dict[str, Any] = {"role": role, "turn_number": row["turn_number"]}
                if row["content"] is not None:
                    msg["content"] = row["content"]
                if role == "assistant" and row["reasoning"] is not None:
                    msg["reasoning"] = row["reasoning"]
                if row["tool_calls"] is not None:
                    try:
                        msg["tool_calls"] = json.loads(row["tool_calls"])
                    except (ValueError, TypeError):
                        pass
                if row["tool_results"] is not None:
                    try:
                        msg["tool_results"] = json.loads(row["tool_results"])
                    except (ValueError, TypeError):
                        pass
                if role == "tool":
                    if row["tool_call_id"]:
                        msg["tool_call_id"] = row["tool_call_id"]
                    if row["tool_name"]:
                        msg["tool_name"] = row["tool_name"]
                if row["step"] is not None:
                    msg["step"] = row["step"]
                if row["substep"] is not None:
                    msg["substep"] = row["substep"]
                messages.append(msg)
            return messages
        except Exception as e:
            log_error(str(e), source="backend/agent/creator_session.py")
            logger.exception("Failed to load creator conversation '%s'", session_id)
            return []
        finally:
            conn.close()

    def get_last_assistant_message(self, session_id: str, turn_number: int) -> dict | None:
        """Return the last assistant message dict of the given turn.

        Args:
            session_id: The creator conversation id.
            turn_number: The turn number to look for.

        Returns:
            The last assistant message dict of that turn, or ``None``.
        """
        messages = self.load_messages(session_id, max_turns=0)
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("turn_number") == turn_number:
                return msg
        return None

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        reasoning: str | None = None,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        status: str | None = None,
        message: str | None = None,
        usage: dict | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        turn_number: int | None = None,
        step: int | None = 0,
        substep: int | None = None,
        setup: dict | None = None,
    ) -> dict:
        """Persist a single row of a creator conversation.

        Args:
            session_id: The creator conversation id.
            role: Message role — ``"user"``, ``"assistant"``, ``"tool"``,
                ``"result"``, ``"call"`` or ``"decisor"``.
            content: Text content of the row.
            reasoning: Reasoning / thinking trace for assistant rows.
            tool_calls: List of tool-call objects (serialised to JSON).
            tool_results: List of tool-result objects (serialised to JSON).
            status: Per-row status (``"success"`` / ``"error"``).
            message: Per-row human-readable message.
            usage: Optional dict with token usage, e.g.
                ``{"prompt_tokens", "completion_tokens", "total_tokens",
                "total_time", "time_to_first_token"}``. Stored in dedicated
                columns with the cost calculated from provider + model.
            tool_call_id: Tool call id (for ``role: "tool"``).
            tool_name: Tool name (for ``role: "tool"``).
            model: LLM model identifier that produced the row.
            provider: Provider name (e.g., "openrouter", "google", "local").
            turn_number: Turn number for grouping rows by conversation turn.
            step: Step within the turn. Always None for role "user".
            substep: Ordinal within the same turn and step.
                Auto-assigned as MAX+1 when None. Always None for "user".
            setup: Setup form of the request (stored as JSON on the first
                user row so the page can rebuild it when reopened).

        Returns:
            A contract response dict indicating success or failure.
        """
        if role not in self.VALID_ROLES:
            return make_error_response(
                message=f"Invalid role '{role}'. Must be one of {sorted(self.VALID_ROLES)}.",
                usage=zero_usage(),
            )

        if isinstance(provider, str):
            provider = provider.strip()

        cost_input = 0.0
        cost_output = 0.0
        cost_total = 0.0
        if provider and model and usage:
            prompt_tokens = (usage or {}).get("prompt_tokens") or 0
            completion_tokens = (usage or {}).get("completion_tokens") or 0
            if prompt_tokens or completion_tokens:
                cost_input, cost_output, cost_total = calculate_cost(
                    provider, model, prompt_tokens, completion_tokens
                )

        conn = self._get_connection()
        try:
            with self._lock:
                if role == "user":
                    step = None
                    substep = None

                if substep is None and step is not None:
                    row = conn.execute(
                        load_query("creators/max_substep.sql"),
                        (session_id, turn_number, step),
                    ).fetchone()
                    substep = int(row[0]) + 1 if row and row[0] is not None else 1

                conn.execute(
                    load_query("creators/insert_row.sql"),
                    (
                        session_id,
                        self.kind,
                        role,
                        content,
                        reasoning,
                        json.dumps(tool_calls) if tool_calls is not None else None,
                        json.dumps(tool_results) if tool_results is not None else None,
                        tool_name,
                        status,
                        message,
                        None,
                        None,
                        None,
                        json.dumps(setup, ensure_ascii=False) if setup is not None else None,
                        provider,
                        model,
                        (usage or {}).get("prompt_tokens"),
                        (usage or {}).get("completion_tokens"),
                        (usage or {}).get("total_tokens"),
                        (usage or {}).get("total_time"),
                        (usage or {}).get("time_to_first_token"),
                        cost_input,
                        cost_output,
                        cost_total,
                        turn_number,
                        step,
                        substep,
                        tool_call_id,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()

            return make_success_response(
                message="Message saved.",
                data={"session_id": session_id, "role": role},
                usage=zero_usage(),
            )
        except Exception as e:
            log_error(str(e), source="backend/agent/creator_session.py")
            logger.exception("Failed to save creator row for '%s'", session_id)
            return make_error_response(
                message=f"Failed to save creator row for '{session_id}'.",
                usage=zero_usage(),
            )
        finally:
            conn.close()

    def update_message_tool_results(
        self, session_id: str, turn_number: int, tool_results: list, step: int | None = None
    ) -> dict:
        """No-op: tool rows already carry their own results.

        The loop calls this after the ordered commit so the frontend can
        display results on history load. Creator history is rebuilt from
        the ``tool`` rows instead, so there is nothing to update.

        Args:
            session_id: The creator conversation id.
            turn_number: The turn number of the assistant message.
            tool_results: List of tool result objects (ignored).
            step: Step of the assistant message that made the calls.

        Returns:
            A contract success response.
        """
        return make_success_response(message="Tool results updated.", usage=zero_usage())

    def save_turn_latency(self, session_id: str, turn_number: int) -> dict:
        """Compute and store the latency of a single creator turn.

        Args:
            session_id: The creator conversation id.
            turn_number: The turn number to measure.

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                row = conn.execute(
                    load_query("creators/turn_latency.sql"),
                    (session_id, turn_number, session_id, turn_number,
                     session_id, turn_number),
                ).fetchone()
                latency = float(row[0]) if row and row[0] is not None else None
                conn.execute(
                    load_query("turn_latency/insert.sql"),
                    (session_id, turn_number, latency),
                )
                conn.commit()
            return make_success_response(message="Latency saved.", usage=zero_usage())
        except Exception as e:
            log_error(str(e), source="backend/agent/creator_session.py")
            logger.exception("Failed to save creator latency for '%s'", session_id)
            return make_error_response(
                message="Failed to save creator latency.",
                usage=zero_usage(),
            )
        finally:
            conn.close()
