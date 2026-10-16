"""Configuration endpoints for the agent loop.

Provides endpoints to:
- Get/set the context window (max turns to keep in context).
- Get/set verbose mode and the initial setup flag.
- List available models per provider, select one and manage its advanced
  parameters (temperature, top_p, reasoning) via ``/models/select`` and
  ``/parameters``.
- Manage provider API keys (list status, save encrypted, delete).
- List skills, tools, agents and MCP servers for the settings panel.

Each topic lives in its own sub-module with its own router; this package
assembles them under a single ``/config`` router.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.routes.config import (
    decision,
    listings,
    models,
    parameters,
    providers,
    runtime,
    workflows,
)
from backend.routes.config.models import get_model_capabilities
from backend.routes.config.providers import refresh_providers_cache
from backend.routes.config.runtime import (
    _detect_and_persist_context_window,
    detect_context_window_background,
    load_persisted_config,
)

__all__ = [
    "router",
    "get_model_capabilities",
    "refresh_providers_cache",
    "detect_context_window_background",
    "load_persisted_config",
    "_detect_and_persist_context_window",
]

router = APIRouter(prefix="/config", tags=["config"])

for _sub in (runtime, providers, parameters, models, decision, listings, workflows):
    router.include_router(_sub.router)
