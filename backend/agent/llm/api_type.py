"""Provider API-type resolution used to dispatch LLM calls."""

from __future__ import annotations

from backend.agent.utils.model_catalog import get_provider_api_type

_LEGACY_API_TYPES: dict[str, str] = {
    "groq": "openai-compatible",
    "openrouter": "openai-compatible",
    "openai": "openai-compatible",
    "deepseek": "openai-compatible",
    "xai": "openai-compatible",
    "togetherai": "openai-compatible",
    "fireworks-ai": "openai-compatible",
    "cerebras": "openai-compatible",
    "mistral": "openai-compatible",
    "perplexity": "openai-compatible",
    "meta": "openai-compatible",
    "moonshotai": "openai-compatible",
    "zhipuai": "openai-compatible",
    "alibaba": "openai-compatible",
    "google": "google",
    "LOCAL": "ollama",
}

"""Fallback name-based API types.

Used only when the local catalog has no rows for the provider (e.g.
sync never ran). Keeps the pre-refactor behavior for the known
providers instead of rejecting them.
"""

def _resolve_api_type(effective_provider: str | None) -> tuple[str, str]:
    """Resolve provider name and API type for LLM dispatch.

    Args:
        effective_provider: Provider name or ``None``.

    Returns:
        Tuple ``(provider, api_type)`` where ``provider`` is the name
        as configured (``""`` when missing) and ``api_type`` is
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"``.
    """
    provider_u = (effective_provider or "").strip()
    api_type = get_provider_api_type(effective_provider or "")
    if api_type == "unknown":
        api_type = _LEGACY_API_TYPES.get(provider_u, "unknown")
    return provider_u, api_type
