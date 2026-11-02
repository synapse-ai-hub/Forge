"""Metrics endpoints for the agent.

Provides REST endpoints that aggregate usage data from the SQLite
``agent.db`` database to power the frontend metrics panel.

Every SQL statement lives as a .sql file under
``backend/agent/agent_db/queries/metrics/<section>/`` — nothing is
hardcoded here. Each endpoint maps 1:1 to its query folder.

Each topic lives in its own sub-module with its own router; this package
assembles them under a single ``metrics`` router.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.routes.metrics import (
    costs,
    creators,
    eda,
    errors,
    feedback,
    messages,
    models,
    overview,
    sessions,
    tools,
    workflows,
)

__all__ = [
    "router",
]

router = APIRouter(tags=["metrics"])

for _sub in (
    sessions,
    messages,
    tools,
    models,
    costs,
    errors,
    workflows,
    creators,
    feedback,
    overview,
    eda,
):
    router.include_router(_sub.router)
