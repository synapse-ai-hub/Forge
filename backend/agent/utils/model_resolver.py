"""Model resolver — Ollama (LOCAL) model discovery and context window.

This module handles **only** the local Ollama provider.  Cloud providers
(curated OpenAI-compatible providers and Google) are now served by
:mod:`model_catalog` which fetches data from models.dev and caches it
in ``agent.db``.

Functions exposed:

- ``get_ollama_models()`` → runs ``ollama list``.
- ``get_ollama_context_window()`` → ``POST /api/show``.
- ``get_vram_gb()`` → detects GPU VRAM.
- ``ollama_default_context()`` → default context length by VRAM.
- ``model_supports_reasoning()`` → LOCAL-only reasoning check.
- ``get_model_reasoning_options()`` → LOCAL-only reasoning options.
- ``ensure_context_window()`` → delegates to model_catalog for cloud.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agent.agent import Agent

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path for absolute imports
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ollama model listing
# ---------------------------------------------------------------------------

def get_ollama_models() -> List[str]:
    """List available models via ``ollama list``.

    Returns:
        A list of model name strings. Empty if ``ollama`` is not installed.
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("ollama list failed: %s", result.stderr.strip())
            return []
    except FileNotFoundError as e:
        log_error(str(e), source="model_resolver.py:get_ollama_models")
        logger.error("ollama binary not found. Is Ollama installed?")
        return []
    except subprocess.TimeoutExpired as e:
        log_error(str(e), source="model_resolver.py:get_ollama_models(timeout)")
        logger.error("ollama list timed out")
        return []

    lines = result.stdout.strip().splitlines()
    if not lines:
        return []

    # Skip header line ("NAME\tID\tSIZE\tMODIFIED")
    models = []
    for line in lines[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0])

    return models


# ---------------------------------------------------------------------------
# Ollama context window
# ---------------------------------------------------------------------------

def get_ollama_context_window(model: str) -> int | None:
    """Return the effective runtime context length (tokens) for an Ollama model.

    Calls ``POST /api/show`` and reads, in order of preference:
    1. the top-level ``context_length``,
    2. ``model_info["<family>.context_length"]``,
    3. ``num_ctx`` parsed from the ``parameters`` string.

    Args:
        model: The Ollama model name.

    Returns:
        The context length in tokens, or ``None`` if it cannot be resolved.
    """
    import requests

    try:
        resp = requests.post(
            "http://localhost:11434/api/show",
            json={"model": model},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        cl = data.get("context_length")
        if cl:
            return int(cl)

        model_info = data.get("model_info") or {}
        for k, v in model_info.items():
            if k.endswith(".context_length") and v:
                return int(v)

        params = data.get("parameters") or ""
        m = re.search(r"num_ctx\s+(\d+)", params)
        if m:
            return int(m.group(1))

        return None
    except Exception as e:
        log_error(str(e), source="model_resolver.py:get_ollama_context_window")
        return None


# ---------------------------------------------------------------------------
# Context window detection (delegates cloud to model_catalog)
# ---------------------------------------------------------------------------

def ensure_context_window(agent: Agent, model: str) -> int | None:
    """Return the model's context window, detecting and caching it if needed.

    If ``agent._context_window`` is already set, returns it. Otherwise it
    detects the context window for the given model and caches it on the
    agent instance.

    - ``LOCAL`` → ``get_ollama_context_window()``
    - Cloud providers → ``model_catalog.get_context_window()``

    Args:
        agent: The ``Agent`` instance (may be ``None``).
        model: The model name.

    Returns:
        The context window in tokens, or ``None`` if it cannot be resolved.
    """
    if agent is not None and getattr(agent, "_context_window", None):
        return agent._context_window

    provider = (getattr(agent, "provider", None) or "LOCAL").strip()
    cw = None
    try:
        if provider == "LOCAL":
            cw = get_ollama_context_window(model)
        else:
            from backend.agent.utils import model_catalog
            cw = model_catalog.get_context_window(provider, model)
    except Exception as e:
        log_error(str(e), source="model_resolver.py:ensure_context_window")
        cw = None

    if cw and agent is not None:
        agent._context_window = cw
    return cw


# ---------------------------------------------------------------------------
# VRAM detection
# ---------------------------------------------------------------------------

_vram_cache: int | None | object = None


def get_vram_gb() -> int | None:
    """Get the total VRAM of the primary GPU.

    Resolution order:
    1. In-memory cache.
    2. Value persisted in ``config_kv``.
    3. Detect via ``nvidia-smi`` then ``wmic`` (Windows).

    Returns:
        The VRAM in GB, or ``None`` if unknown.
    """
    global _vram_cache
    if _vram_cache is not None:
        return _vram_cache if isinstance(_vram_cache, int) else None

    try:
        from backend.instances import session_manager

        persisted = (
            session_manager.get_config("vram_gb")
            if session_manager is not None
            else None
        )
        if persisted is not None:
            vram = int(persisted)
            _vram_cache = vram
            return vram
    except Exception:
        pass

    vram = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            first = result.stdout.strip().splitlines()[0].strip()
            vram = int(float(first) / 1024)
    except Exception:
        vram = None

    if vram is None:
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "AdapterRAM"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.isdigit():
                        vram = int(int(line) / (1024**3))
                        break
        except Exception:
            vram = None

    if vram is not None:
        try:
            from backend.instances import session_manager

            if session_manager is not None:
                session_manager.set_config("vram_gb", str(vram))
        except Exception:
            pass

    _vram_cache = vram if vram is not None else -1
    return vram


def ollama_default_context(vram_gb: int | None) -> int | None:
    """Return the default context length Ollama configures for a given VRAM.

    Args:
        vram_gb: Total VRAM in GB, or ``None`` if unknown.

    Returns:
        The default context length in tokens, or ``None`` if VRAM is unknown.
    """
    if vram_gb is None:
        return None
    if vram_gb < 24:
        return 4096
    if vram_gb < 48:
        return 32768
    return 262144


# ---------------------------------------------------------------------------
# LOCAL reasoning support (Ollama only — cloud uses model_catalog)
# ---------------------------------------------------------------------------

def model_supports_reasoning(provider: str, model: str) -> bool | None:
    """Return whether a LOCAL (Ollama) model supports reasoning.

    Cloud providers are handled by ``model_catalog.get_reasoning_options()``.

    Args:
        provider: Provider name (only ``"LOCAL"`` is meaningful here).
        model: The model name.

    Returns:
        ``True`` if the model supports reasoning, ``False`` if not,
        ``None`` when unknown or provider is not LOCAL.
    """
    if not provider or not model:
        return None
    if provider.strip() != "LOCAL":
        return None

    model_lower = model.lower()
    # Known reasoning models in Ollama
    if any(tag in model_lower for tag in ("qwen3", "qwen-3", "deepseek", "gpt-oss", "gemma-4", "gemma4")):
        return True
    return None


def get_model_reasoning_options(provider: str, model: str) -> dict:
    """Return reasoning options for a LOCAL (Ollama) model.

    Cloud providers are handled by ``model_catalog.get_reasoning_options()``.

    Args:
        provider: Provider name (only ``"LOCAL"`` is meaningful here).
        model: The model name.

    Returns:
        Dict with ``reasoning_supported``, ``reasoning_options``,
        ``reasoning_param``, ``reasoning_type``,
        ``response_format_supported``, plus model info.
    """
    result = {
        "reasoning_supported": None,
        "reasoning_options": [],
        "reasoning_param": None,
        "reasoning_type": "boolean",
        "response_format_supported": None,
    }

    if not provider or not model:
        return result

    p = provider.strip()
    if p != "LOCAL":
        return result

    # Ollama supports structured output via ``format: json``.
    result["response_format_supported"] = True

    # Get model info from Ollama /api/show
    import requests
    try:
        resp = requests.post(
            "http://localhost:11434/api/show",
            json={"model": model},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Context window: try multiple sources
        cl = data.get("context_length")
        if cl:
            result["context_window"] = int(cl)
        else:
            model_info = data.get("model_info") or {}
            for k, v in model_info.items():
                if k.endswith(".context_length") and v:
                    result["context_window"] = int(v)
                    break
            else:
                # Try parsing from parameters
                params = data.get("parameters") or ""
                import re
                m = re.search(r"num_ctx\s+(\d+)", params)
                if m:
                    result["context_window"] = int(m.group(1))

        # Modalities from capabilities
        caps = data.get("capabilities") or []
        if "vision" in caps:
            result["input_modalities"] = ["text", "image"]
        else:
            result["input_modalities"] = ["text"]
        result["output_modalities"] = ["text"]
    except Exception:
        pass

    # Only include fields with actual values
    result = {k: v for k, v in result.items() if v is not None and v != []}

    model_lower = model.lower()

    try:
        # GPT-OSS models: string levels only (low/medium/high)
        if "gpt-oss" in model_lower:
            result["reasoning_supported"] = True
            result["reasoning_param"] = "think_level"
            result["reasoning_type"] = "levels"
            result["reasoning_options"] = [
                {"value": "low", "label": "Bajo"},
                {"value": "medium", "label": "Medio"},
                {"value": "high", "label": "Alto"},
            ]
        # Qwen 3: boolean + levels (thinking ON by default)
        elif "qwen3" in model_lower or "qwen-3" in model_lower:
            result["reasoning_supported"] = True
            result["reasoning_param"] = "think"
            result["reasoning_type"] = "boolean"
            result["reasoning_options"] = [
                {"value": "on", "label": "Activado (default)"},
                {"value": "off", "label": "Desactivado"},
                {"value": "low", "label": "Bajo"},
                {"value": "medium", "label": "Medio"},
                {"value": "high", "label": "Alto"},
                {"value": "max", "label": "Máximo"},
            ]
        # DeepSeek R1: boolean (thinking always-on)
        elif "deepseek" in model_lower:
            result["reasoning_supported"] = True
            result["reasoning_param"] = "think"
            result["reasoning_type"] = "boolean"
            result["reasoning_options"] = [
                {"value": "on", "label": "Activado (siempre activo)"},
                {"value": "off", "label": "Desactivado"},
            ]
        # Gemma 4: boolean
        elif "gemma-4" in model_lower or "gemma4" in model_lower:
            result["reasoning_supported"] = True
            result["reasoning_param"] = "think"
            result["reasoning_type"] = "boolean"
            result["reasoning_options"] = [
                {"value": "on", "label": "Activado"},
                {"value": "off", "label": "Desactivado"},
            ]
        else:
            result["reasoning_supported"] = False
            result["reasoning_options"] = [
                {"value": "default", "label": "Default"},
            ]

    except Exception as e:
        log_error(str(e), source="model_resolver.py:get_model_reasoning_options")
        return result

    return result
