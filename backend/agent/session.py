"""SQLite-based session persistence for the agent loop.

Provides the ``SessionManager`` class to persist conversation sessions
and messages in a local SQLite database with thread-safe writes.
"""

import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error
from backend.agent.ddl_setup import setup_database
from backend.agent.utils.db import DB_PATH
from backend.agent.utils.queries import load_query
from backend.agent.utils.spend_handler import calculate_cost

logger = logging.getLogger(__name__)


class SessionManager:
    """Persists conversation sessions and messages in SQLite.

    All write operations are protected by a ``threading.RLock`` so the
    same instance can be safely shared across threads.

    Attributes:
        db_path: Path to the SQLite database file.
        conn: Lazy-initialised SQLite connection (``None`` until first use).
        _lock: Thread lock for write serialisation.
        _initialized: Whether the database tables have been created.
    """

    VALID_ROLES = frozenset({"system", "user", "assistant", "tool", "title"})

    def __init__(self, db_path: str = DB_PATH) -> None:
        """Initialise the session manager.

        Connections are now created per-operation (not singleton) to avoid
        transaction state leaking across operations (which caused hangs on
        refresh after cancellation).

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection for each operation.

        Creates the parent directory, opens the connection, sets
        optimised PRAGMAs, and creates tables if they do not exist yet.
        Each call returns a fresh connection to avoid transaction state
        leaking across operations (which caused hangs on refresh after cancellation).

        Returns:
            A new ``sqlite3.Connection`` instance.
        """
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables(conn)
        return conn

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create all agent tables using the canonical schema from ddl_setup.

        Args:
            conn: The open SQLite connection to run DDL on.
        """
        setup_database(conn)

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def create_session(
        self, session_id: str, metadata: dict | None = None, parent_id: str | None = None
    ) -> dict:
        """Create a new session.

        Args:
            session_id: Unique identifier for the session.
            metadata: Optional arbitrary metadata to store as JSON.
            parent_id: Optional parent session identifier (for sub-agents).

        Returns:
            A contract response dict indicating success or failure.
        """
        try:
            with self._lock:
                conn = self._get_connection()
                try:
                    existing = conn.execute(
                        load_query("sessions/exists.sql"),
                        (session_id,),
                    ).fetchone()

                    if existing is not None:
                        return make_error_response(
                            message=f"Session '{session_id}' already exists.",
                            usage=zero_usage(),
                        )

                    now = datetime.now().isoformat()
                    metadata_json = json.dumps(metadata) if metadata is not None else None

                    conn.execute(
                        load_query("sessions/create.sql"),
                        (session_id, now, now, metadata_json, parent_id),
                    )
                    conn.commit()

                finally:
                    conn.close()

            return make_success_response(
                message="Session created.",
                data={"session_id": session_id},
                usage=zero_usage(),
            )
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to create session '%s'", session_id)
            return make_error_response(
                message=f"Failed to create session '{session_id}'.",
                usage=zero_usage(),
            )

    def load_messages(self, session_id: str, max_turns: int = -1) -> list[dict]:
        """Load messages for a session in chronological order.

        Args:
            session_id: The session identifier.
            max_turns: Number of most recent turns to load.
                ``-1`` (default) loads all messages.
                ``0`` loads only messages from the current (unfinished) turn.
                ``N`` loads the last N complete turns plus any messages
                from the current incomplete turn.

        Returns:
            List of message dicts, each with ``tool_calls`` and
            ``tool_results`` deserialised from JSON (when not null).
            Returns an empty list if the session does not exist or has
            no messages.
        """
        conn = self._get_connection()
        try:
            if max_turns <= 0:
                # Load ALL messages
                rows = conn.execute(
                    load_query("messages/load_all.sql"),
                    (session_id,),
                ).fetchall()
            else:
                # Find the max turn_number for this session
                row = conn.execute(
                    load_query("messages/get_max_turn.sql"),
                    (session_id,),
                ).fetchone()
                max_turn = row["max_turn"] if row and row["max_turn"] is not None else 0

                min_turn = max(max_turn - max_turns + 1, 0)
                # +1 to include the current incomplete turn as well
                rows = conn.execute(
                    load_query("messages/load_from_turn.sql"),
                    (session_id, min_turn),
                ).fetchall()

            messages: list[dict] = []
            for row in rows:
                msg = dict(row)
                if msg.get("tool_calls") is not None:
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                if msg.get("tool_results") is not None:
                    msg["tool_results"] = json.loads(msg["tool_results"])
                messages.append(msg)

            return messages
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception(
                "Failed to load messages for session '%s'", session_id
            )
            return []
        finally:
            conn.close()

    def get_last_assistant_message(self, session_id: str, turn_number: int) -> dict | None:
        """Return the last assistant message dict of the given turn.

        Shared by the chat route and the scheduler to read the final assistant
        answer (content) or its persisted status without duplicating the
        reverse-scan over ``load_messages``.

        Args:
            session_id: The session identifier.
            turn_number: The turn number to look for.

        Returns:
            The last assistant message dict of that turn, or ``None`` if none.
        """
        messages = self.load_messages(session_id, max_turns=0)
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("turn_number") == turn_number:
                return msg
        return None

    def get_session_metadata(self, session_id: str) -> dict:
        """Load the metadata JSON of a session.

        Args:
            session_id: The session identifier.

        Returns:
            The metadata dict, or ``{}`` if the session does not exist
            or has no metadata.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                load_query("sessions/get_metadata.sql"),
                (session_id,),
            ).fetchone()
            if not row or not row["metadata"]:
                return {}
            result = json.loads(row["metadata"])
            return result if isinstance(result, dict) else {}
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception(
                "Failed to load metadata for session '%s'", session_id
            )
            return {}
        finally:
            conn.close()

    def get_session_title(self, session_id: str) -> str:
        """Return the stored title of a session.

        Args:
            session_id: The session identifier.

        Returns:
            The stored title, or an empty string when the session does not
            exist or has no title yet.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                load_query("sessions/get_title.sql"),
                (session_id,),
            ).fetchone()
            if not row or not row["title"]:
                return ""
            return str(row["title"])
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py:get_session_title")
            logger.exception(
                "Failed to load title for session '%s'", session_id
            )
            return ""
        finally:
            conn.close()

    def list_sessions(self) -> list[dict]:
        """List all sessions ordered by most recent activity.

        Returns:
            A list of session dicts, each with ``session_id``,
            ``created_at``, ``updated_at``, ``title`` (stored or derived from the
            first user message), ``preview`` (first user message content),
            and ``message_count``. Returns an empty list on failure.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(load_query("sessions/list_sessions.sql")).fetchall()

            sessions: list[dict] = []
            for row in rows:
                session_id = row["session_id"]

                preview_row = conn.execute(
                    load_query("messages/first_user_content.sql"),
                    (session_id,),
                ).fetchone()
                first_user = (
                    preview_row["content"]
                    if preview_row and preview_row["content"]
                    else ""
                )

                stored_title = row["title"]
                title = (
                    stored_title
                    if stored_title
                    else (first_user.strip().split("\n")[0][:60] if first_user else "Nueva conversación")
                )

                count_row = conn.execute(
                    load_query("messages/count_by_session.sql"),
                    (session_id,),
                ).fetchone()
                message_count = int(count_row["cnt"]) if count_row else 0

                sessions.append(
                    {
                        "session_id": session_id,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "title": title,
                        "preview": first_user[:120],
                        "message_count": message_count,
                    }
                )
            return sessions
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to list sessions")
            return []
        finally:
            conn.close()

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
    ) -> dict:
        """Persist a single message and update the session timestamp.

        Args:
            session_id: The session identifier.
            role: Message role — must be one of ``"system"``,
                ``"user"``, ``"assistant"``, ``"tool"``.
            content: Text content of the message (optional for tool
                roles).
            reasoning: Reasoning / thinking trace for assistant messages.
            tool_calls: List of tool-call objects (serialised to JSON).
            tool_results: List of tool-result objects (serialised to
                JSON).
            status: Per-message status (``"success"`` / ``"error"``).
            message: Per-message human-readable message.
            usage: Optional dict with token usage, e.g.
                ``{"prompt_tokens", "completion_tokens", "total_tokens",
                "total_time", "time_to_first_token"}``. Stored in dedicated columns.
            tool_call_id: Tool call ID (OpenAI-compatible format, for ``role: "tool"``).
            tool_name: Tool name (Ollama format, for ``role: "tool"``).
            model: LLM model identifier that produced the message
                (assistant messages only; ``None`` otherwise).
            provider: Provider name (e.g., "openrouter", "google", "local").
                Used to calculate cost per message when combined with model and usage.
            turn_number: Turn number for grouping messages by
                conversation turn.
            step: Step within the turn. Always None for roles
                "user" and "title" (those messages carry no step).
            substep: Ordinal within the same turn and step
                (differentiates parallel messages sharing a step).
                Auto-assigned as MAX+1 when None. Always None for
                roles "user" and "title".

        Returns:
            A contract response dict indicating success or failure.
        """
        if role not in self.VALID_ROLES:
            return make_error_response(
                message=f"Invalid role '{role}'. Must be one of {sorted(self.VALID_ROLES)}.",
                usage=zero_usage(),
            )

        # Canonical storage: provider exactly as configured (models.dev id).
        if isinstance(provider, str):
            provider = provider.strip()

        # Calculate cost if provider, model, and usage are available
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
                now = datetime.now().isoformat()

                if role in ("user", "title"):
                    step = None
                    substep = None

                if substep is None and step is not None:
                    row = conn.execute(
                        load_query("messages/get_max_substep.sql"),
                        (session_id, turn_number, step),
                    ).fetchone()
                    substep = int(row[0]) + 1 if row else 1

                conn.execute(
                    load_query("messages/insert.sql"),
                    (
                        session_id,
                        role,
                        content,
                        reasoning,
                        json.dumps(tool_calls) if tool_calls is not None else None,
                        json.dumps(tool_results) if tool_results is not None else None,
                        status,
                        message,
                        (usage or {}).get("prompt_tokens"),
                        (usage or {}).get("completion_tokens"),
                        (usage or {}).get("total_tokens"),
                        (usage or {}).get("total_time"),
                        (usage or {}).get("time_to_first_token"),
                        tool_call_id,
                        tool_name,
                        model,
                        provider,
                        cost_input,
                        cost_output,
                        cost_total,
                        turn_number,
                        step,
                        substep,
                        now,
                    ),
                )
                conn.execute(
                    load_query("sessions/update_updated_at.sql"),
                    (now, session_id),
                )
                conn.commit()

            return make_success_response(
                message="Message saved.",
                data={"session_id": session_id, "role": role},
                usage=zero_usage(),
            )
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception(
                "Failed to save message for session '%s'", session_id
            )
            return make_error_response(
                message=f"Failed to save message for session '{session_id}'.",
                usage=zero_usage(),
            )
        finally:
            conn.close()

    def save_turn_latency(self, session_id: str, turn_number: int) -> dict:
        """Compute and store the latency of a single turn.

        Latency = SUM(assistant total_time for steps before the last one)
            + SUM over steps of MAX(tool total_time)
            + time_to_first_token of the last assistant message.
        Each part is COALESCEd to 0: a missing part (e.g. a direct
        answer with no tool steps) does not null the other parts.

        Args:
            session_id: The session identifier.
            turn_number: The turn number to compute.

        Returns:
            A contract response dict with the stored latency.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                row = conn.execute(
                    load_query("turn_latency/compute.sql"),
                    (
                        session_id, turn_number,
                        session_id, turn_number,
                        session_id, turn_number,
                        session_id, turn_number,
                    ),
                ).fetchone()
                latency = row[0] if row else None
                conn.execute(
                    load_query("turn_latency/insert.sql"),
                    (session_id, turn_number, latency),
                )
                conn.commit()
            return make_success_response(
                message="Turn latency saved.",
                data={"session_id": session_id, "turn_number": turn_number, "latency": latency},
                usage=zero_usage(),
            )
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception(
                "Failed to save turn latency for session '%s' turn %s", session_id, turn_number
            )
            return make_error_response(
                message=f"Failed to save turn latency for session '{session_id}'.",
                usage=zero_usage(),
            )
        finally:
            conn.close()

    def get_last_turn_number(self, session_id: str) -> int:
        """Return the highest ``turn_number`` stored for a session.

        Args:
            session_id: The session identifier.

        Returns:
            The maximum ``turn_number`` or ``0`` if no messages exist.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                load_query("messages/get_max_turn_or_zero.sql"),
                (session_id,),
            ).fetchone()
            return int(row["max_turn"]) if row else 0
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to get last turn for '%s'", session_id)
            return 0
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> dict:
        """Delete a session and all its messages.

        Args:
            session_id: The session identifier to remove.

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                conn.execute(
                    load_query("messages/delete_by_session.sql"),
                    (session_id,),
                )

                cursor = conn.execute(
                    load_query("sessions/delete_session.sql"),
                    (session_id,),
                )

                if cursor.rowcount == 0:
                    return make_error_response(
                        message=f"Session '{session_id}' not found.",
                        usage=zero_usage(),
                    )

                conn.commit()

            return make_success_response(
                message=f"Session '{session_id}' deleted.",
                usage=zero_usage(),
            )
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception(
                "Failed to delete session '%s'", session_id
            )
            return make_error_response(
                message=f"Failed to delete session '{session_id}'.",
                usage=zero_usage(),
            )
        finally:
            conn.close()

    def get_config(self, key: str) -> str | None:
        """Read a value from the key-value config store.

        Args:
            key: The configuration key to look up.

        Returns:
            The stored value as a string, or ``None`` if the key does not
            exist or an error occurs.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                row = conn.execute(
                    load_query("config/get_value.sql"), (key,)
                ).fetchone()
            return row["value"] if row else None
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to get config '%s'", key)
            return None
        finally:
            conn.close()

    def set_config(self, key: str, value: str) -> dict:
        """Persist a key-value pair in the config store (UPSERT).

        Args:
            key: The configuration key to store.
            value: The value to store (coerced to ``str``).

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                conn.execute(
                    load_query("config/upsert_value.sql"),
                    (key, value),
                )
                conn.commit()
            return make_success_response(message="Config saved.", usage=zero_usage())
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to set config '%s'", key)
            return make_error_response(message="Failed to set config.", usage=zero_usage())
        finally:
            conn.close()

    def get_providers(self) -> list[dict]:
        """Return all cached providers with their model lists.

        Returns:
            A list of dicts with ``provider``, ``label`` and ``models`` keys.
            Empty list on failure or if none are cached.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(load_query("providers/list.sql")).fetchall()
            result: list[dict] = []
            for row in rows:
                models = json.loads(row["models"]) if row["models"] else []
                result.append(
                    {
                        "provider": row["provider"],
                        "label": row["label"],
                        "models": models,
                    }
                )
            return result
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to load providers cache")
            return []
        finally:
            conn.close()

    def save_providers(self, providers: list[dict]) -> dict:
        """UPSERT the provider cache (provider, label, models).

        Args:
            providers: List of dicts with ``provider``, ``label`` and ``models``.

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                now = datetime.now().isoformat()
                for p in providers:
                    conn.execute(
                        load_query("providers/upsert.sql"),
                        (p["provider"], p["label"], json.dumps(p.get("models") or []), now),
                    )
                conn.commit()
            return make_success_response(message="Providers cache saved.", usage=zero_usage())
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to save providers cache")
            return make_error_response(message="Failed to save providers cache.", usage=zero_usage())
        finally:
            conn.close()

    def update_session_title(self, session_id: str, title: str) -> dict:
        """Update the title of a session.

        Args:
            session_id: The session identifier.
            title: The new title to set.

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                conn.execute(
                    load_query("sessions/update_title.sql"),
                    (title, session_id),
                )
                conn.commit()
            return make_success_response(message="Title updated.", usage=zero_usage())
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to update title for '%s'", session_id)
            return make_error_response(message="Failed to update title.", usage=zero_usage())
        finally:
            conn.close()

    def update_message_tool_results(self, session_id: str, turn_number: int, tool_results: list) -> dict:
        """Update the assistant message's tool_results for a given turn.

        Args:
            session_id: The session identifier.
            turn_number: The turn number of the assistant message.
            tool_results: List of tool result objects to store.

        Returns:
            A contract response dict indicating success or failure.
        """
        conn = self._get_connection()
        try:
            with self._lock:
                conn.execute(
                    load_query("messages/update_tool_results.sql"),
                    (json.dumps(tool_results), session_id, turn_number),
                )
                conn.commit()
            return make_success_response(message="Tool results updated.", usage=zero_usage())
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to update tool results for session '%s' turn %d", session_id, turn_number)
            return make_error_response(message="Failed to update tool results.", usage=zero_usage())
        finally:
            conn.close()

    def get_all_titles(self) -> list[str]:
        """Return all existing session titles (non-empty).

        Returns:
            A list of title strings, or an empty list on failure.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(load_query("sessions/list_titles.sql")).fetchall()
            return [row["title"] for row in rows]
        except Exception as e:
            log_error(str(e), source="backend/agent/session.py")
            logger.exception("Failed to load existing titles")
            return []
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op: connections are now per-operation and closed automatically."""
        pass
