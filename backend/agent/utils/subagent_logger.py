"""Custom SUBAGENT log level, displayed in yellow.

Usage::

    logger.subagent("agent=%s ...", agent_name, ...)

The output appears as::

    2026-07-15 ... - backend.agent.loop - SUBAGENT - agent=...

where ``SUBAGENT`` is rendered in **yellow** (ANSI escape codes).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

SUBAGENT_LEVEL = 25
"""Numeric level for SUBAGENT (INFO=20, WARNING=30)."""

logging.addLevelName(SUBAGENT_LEVEL, "SUBAGENT")


def _subagent(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a message with SUBAGENT level.

    Args:
        message: The message template.
        *args: Format arguments.
        **kwargs: Extra keyword arguments forwarded to ``log()``.
    """
    self.log(SUBAGENT_LEVEL, message, *args, **kwargs)


logging.Logger.subagent = _subagent  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ANSI-yellow colour for SUBAGENT level in the log output
#
# The root logger (configured by uvicorn) uses logging.Formatter, which does
# NOT colour level names.  Instead we install a Filter that wraps the level
# name in ANSI escape codes when stderr is a terminal.
# ---------------------------------------------------------------------------
class _SubagentColorFilter(logging.Filter):
    """Add ANSI yellow colour to SUBAGENT level name in the LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Color the level name of sub-agent records when the terminal supports it.

        Args:
            record: The log record.

        Returns:
            Always True: the record is never dropped.
        """
        if record.levelno == SUBAGENT_LEVEL and sys.stderr.isatty():
            record.levelname = "\033[33mSUBAGENT\033[0m"
        return True


# Apply to the root logger so every handler benefits
logging.getLogger().addFilter(_SubagentColorFilter())
