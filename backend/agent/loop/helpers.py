"""Loop helpers: tool API type, router permissions and advanced-parameter overrides."""

from __future__ import annotations

import logging
from typing import Any

import yaml

from backend.agent.utils.error_logger import log_error
from backend.agent.utils import provider_keys
from backend.agent.utils.model_catalog import get_provider_api_type
from backend.instances import session_manager

logger = logging.getLogger(__name__)

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

def _load_router_permissions() -> dict | None:
    """Load the router's permissions from ``~/.config/synapseForge/config.yaml``.

    Reads the ``permissions`` section (same structure as agent frontmatter:
    ``tools``, ``skills`` and ``tasks`` sub-blocks, always plural).

    Returns:
        The ``permissions`` dict, or ``None`` if the file does not exist,
        has no ``permissions`` section, or cannot be read.
    """
    from backend.agent.utils.config_dir import get_config_dir

    cfg_path = get_config_dir() / "config.yaml"
    if not cfg_path.is_file():
        return None
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        log_error(str(exc), source="loop.py:_load_router_permissions")
        return None
    perms = data.get("permissions")
    return perms if isinstance(perms, dict) else None

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
