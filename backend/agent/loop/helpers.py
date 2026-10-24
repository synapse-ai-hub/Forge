"""Loop helpers: tool API type, router permissions and advanced-parameter overrides."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.agent.utils.error_logger import log_error
from backend.agent.utils import provider_keys
from backend.agent.utils.model_catalog import get_provider_api_type
from backend.agent.utils.rag_helpers import HELP_COLLECTION, MEMORY_COLLECTION
from backend.instances import session_manager

logger = logging.getLogger(__name__)

# Internal RAG collections the router can always query (help and conversation
# memory), whatever the stored selection says.
_ROUTER_RAG_FLOOR = {HELP_COLLECTION: "allow", MEMORY_COLLECTION: "allow"}

def _resolve_tool_api_type(effective_provider: str | None) -> str:
    """Resolve the API type used to pick the tool-message format.

    Reads the synced catalog first and falls back to the curated
    ``provider_keys.PROVIDER_REGISTRY`` when the catalog has no rows
    for the provider (sync never ran).

    Args:
        effective_provider: Provider name or ``None``.

    Returns:
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"``.
    """
    try:
        api_type = get_provider_api_type(effective_provider or "")
    except Exception:
        api_type = "unknown"
    if api_type == "unknown":
        try:
            info = provider_keys.PROVIDER_REGISTRY.get(
                (effective_provider or "").strip(), {}
            )
            api_type = str(info.get("api_type") or "unknown")
        except Exception:
            api_type = "unknown"
    return api_type

# Columns of the ``router_config`` single-row table, in panel order.
_ROUTER_SELECTION_KEYS = ("agentes", "tools", "skills", "rag")


def _parse_name_list(raw: Any) -> list[str]:
    """Parse a ``router_config`` column into a sorted list of names.

    Args:
        raw: Column value (a JSON array stored as text).

    Returns:
        Sorted, de-duplicated list of non-empty names (empty when the
        value is missing or unparseable).
    """
    if not isinstance(raw, str) or not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return sorted({str(n) for n in value if isinstance(n, str) and n})


def load_router_selection_with_source() -> tuple[dict[str, list[str]] | None, str]:
    """Load the router's selection and report where it came from.

    Reads the single row of the ``router_config`` table (written by the
    sidebar panel). There is no file fallback: without a row the floor
    defaults apply.

    Returns:
        A ``(selection, source)`` tuple: the ``{"agentes", "tools",
        "skills", "rag"}`` lists (or ``None`` when no row exists) and
        ``source`` (``"db"`` or ``"floor"``).
    """
    try:
        row = session_manager.get_router_config()
    except Exception as exc:
        log_error(str(exc), source="loop/helpers.py:load_router_selection(db)")
        row = None
    if row is None:
        return None, "floor"
    selection: dict[str, list[str]] = {}
    corrupt: list[str] = []
    for key in _ROUTER_SELECTION_KEYS:
        raw = row.get(key)
        parsed = _parse_name_list(raw)
        selection[key] = parsed
        if not parsed and isinstance(raw, str) and raw.strip() not in ("", "[]"):
            corrupt.append(key)
    if corrupt:
        log_error(
            "router_config has unparseable JSON in column(s): " + ", ".join(corrupt),
            source="loop/helpers.py:load_router_selection",
        )
    if len(corrupt) == len(_ROUTER_SELECTION_KEYS):
        return None, "floor"
    return selection, "db"


def _load_router_permissions() -> dict[str, Any] | None:
    """Load the router's permissions from the ``router_config`` table.

    Returns:
        The permissions dict (``tools``, ``tasks``, ``skills`` and
        ``rag`` sub-blocks mapping names to ``"allow"``), or ``None``
        when no row exists (floor defaults apply). See
        :func:`load_router_selection_with_source` for the source-aware
        variant.
    """
    selection, _ = load_router_selection_with_source()
    if selection is None:
        return None
    return selection_to_router_perms(selection)


def save_router_selection(selection: dict[str, Any]) -> bool:
    """Persist the router's selection in the ``router_config`` table.

    Args:
        selection: ``{"agentes", "tools", "skills", "rag"}`` lists of
            names (non-string or empty items are dropped).

    Returns:
        ``True`` when the row was stored.
    """
    try:
        payload = {
            key: json.dumps(
                sorted(
                    {
                        str(n)
                        for n in (selection.get(key) or [])
                        if isinstance(n, str) and n
                    }
                )
            )
            for key in _ROUTER_SELECTION_KEYS
        }
        result = session_manager.save_router_config(
            payload["agentes"], payload["tools"], payload["skills"], payload["rag"]
        )
        return isinstance(result, dict) and result.get("status") == "success"
    except Exception as exc:
        log_error(str(exc), source="loop/helpers.py:save_router_selection")
        return False


def selection_to_router_perms(selection: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Convert the pick lists of the sidebar panel to a permissions dict.

    Args:
        selection: ``{"agentes", "tools", "skills", "rag"}`` lists of names.

    Returns:
        Permissions dict (names mapped to ``"allow"``).
    """
    def _allow(names: Any) -> dict[str, str]:
        if not isinstance(names, list):
            return {}
        return {str(n): "allow" for n in names if isinstance(n, str) and n}

    return {
        "tools": _allow(selection.get("tools")),
        "tasks": _allow(selection.get("agentes")),
        "skills": _allow(selection.get("skills")),
        "rag": _allow(selection.get("rag")),
    }


def _router_tool_permissions(router_perms: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the router's tool permissions.

    If permissions are defined (single row of the ``router_config``
    table) they are used exclusively: ``tools`` become flat permissions,
    ``tasks`` the nested ``task`` permission and ``rag`` the nested
    ``rag`` permission. Without permissions the guaranteed floor tools
    are used. In both cases the internal RAG collections
    (``_ROUTER_RAG_FLOOR``) are always readable, whatever the stored
    selection says. Non-dict values are tolerated: only dict values are
    applied.

    Args:
        router_perms: Result of :func:`_load_router_permissions`.

    Returns:
        The tool permission dict for ``tools_registry``.
    """
    if not router_perms:
        tool_permissions: dict[str, Any] = {
            "task": "allow",
            "search_memory": "allow",
            "read": "allow",
            "websearch": "allow",
            "webfetch": "allow",
        }
    else:
        tool_permissions = {}
        tools_perms = router_perms.get("tools")
        if isinstance(tools_perms, dict):
            for name, action in tools_perms.items():
                tool_permissions[name] = action
        tasks_perms = router_perms.get("tasks")
        if isinstance(tasks_perms, dict) and tasks_perms:
            tool_permissions["task"] = tasks_perms
        rag_perms = router_perms.get("rag")
        if isinstance(rag_perms, dict):
            tool_permissions["rag"] = rag_perms

    # Floor that is never removed nor overridden by the stored selection.
    rag_perms = tool_permissions.get("rag")
    if isinstance(rag_perms, dict):
        tool_permissions["rag"] = {**rag_perms, **_ROUTER_RAG_FLOOR}
    else:
        tool_permissions["rag"] = dict(_ROUTER_RAG_FLOOR)
    # The skill loader is floor too: always available to the router, never
    # shown in the UI (hidden) and never toggled by the stored selection.
    tool_permissions["skill"] = "allow"
    return tool_permissions

def _read_param_override(key: str) -> Any:
    """Read a global advanced-parameter override from ``config_kv``.

    Reads the value persisted by ``POST /api/config/models/select``
    (keys ``param_temperature``, ``param_top_p``, ``param_reasoning``,
    ``param_budget_tokens``, ``param_response_format``).
    The literal string ``"null"`` (or a missing/unparseable key) means
    "default" → returns ``None`` so the caller falls back to the next
    level of the precedence chain.

    Args:
        key: ``config_kv`` key to read.

    Returns:
        The parsed override value (``float`` for temperature/top_p,
        ``bool`` for reasoning, ``str`` for response_format) or ``None``
        when there is no explicit override.
    """
    try:
        raw = session_manager.get_config(key)
    except Exception as exc:
        logger.warning("No se pudo leer el parámetro %s: %s", key, exc)
        return None
    if raw is None or raw.strip().lower() == "null":
        return None
    try:
        if key == "param_reasoning":
            # Can be boolean (old format) or string (new format: "on"/"off"/"low"/"medium"/"high"/"max"/"default"/"none"/"0"/"1024"/etc.)
            val = raw.strip().lower()
            if val in ("true", "on"):
                return "on"
            elif val in ("false", "off"):
                return "off"
            else:
                return raw.strip()
        if key == "param_response_format":
            return raw.strip().lower()
        return float(raw)
    except (TypeError, ValueError):
        return None
