"""Agent loop package for the <nombre>nombre_proyecto</nombre>.

Contains the while(true) agent loop, SQLite session persistence,
context management, and compaction configuration.
"""

from __future__ import annotations

import logging
import os 
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Register custom SUBAGENT log level (must be imported early, before any usage)
try:
    from backend.agent.utils.subagent_logger import SUBAGENT_LEVEL as _SUBAGENT_LEVEL
except ImportError:
    pass

from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

# Lazy imports — submodules are created in separate tasks
try:
    from backend.agent.utils.config import CompactionConfig, SessionContext
except ImportError as e:
    log_error(str(e), source="agent/__init__.py(config)")
    CompactionConfig = None  # type: ignore
    SessionContext = None  # type: ignore
    logger.debug("backend.agent.config not yet available")

try:
    from backend.agent.session import SessionManager
except ImportError as e:
    log_error(str(e), source="agent/__init__.py(session)")
    SessionManager = None  # type: ignore
    logger.debug("backend.agent.session not yet available")


def __getattr__(name: str) -> type[AgentLoop]:
    """Lazily resolve attributes that cannot be imported eagerly.

    ``AgentLoop`` is resolved lazily because ``backend.agent.loop``
    imports ``backend.instances``, which in turn imports this package.
    Importing the loop module eagerly here would create a circular
    import during ``backend.instances`` initialization.

    Args:
        name: Attribute name being accessed on the package.

    Returns:
        The requested attribute.

    Raises:
        AttributeError: If the attribute is not exposed by the package.
    """
    if name == "AgentLoop":
        from backend.agent.loop import AgentLoop

        return AgentLoop
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CompactionConfig",
    "SessionContext",
    "SessionManager",
    "ContextManager",
    "AgentLoop",
]
