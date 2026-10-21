"""Agent loop configuration loaded from environment variables.

Allows the user to tune compaction behaviour (trigger threshold,
strategy, tail turns, preserve tokens, etc.) without changing code.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

    
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)


def _to_bool(value: str | None, default: bool) -> bool:
    """Parse a bool env var.

    Args:
        value: The raw value, or None when unset.
        default: Value to return when it is unset.

    Returns:
        The parsed bool, or ``default`` if unset.
    """
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _to_int(value: str | None, default: int) -> int:
    """Parse an int env var.

    Args:
        value: The raw value, or None when unset.
        default: Value to return when it is unset or invalid.

    Returns:
        The parsed int, or ``default`` if unset/invalid.
    """
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        log_error(str(e), source="config.py:_to_int")
        return default


def _to_float(value: str | None, default: float) -> float:
    """Parse a float env var.

    Args:
        value: The raw value, or None when unset.
        default: Value to return when it is unset or invalid.

    Returns:
        The parsed float, or ``default`` if unset/invalid.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        log_error(str(e), source="config.py:_to_float")
        return default


VALID_STRATEGIES: tuple[str, ...] = ("ask", "cod", "original")


@dataclass
class CompactionConfig:
    """Global compaction configuration for the agent loop.

    All fields are loaded from environment variables (with sensible
    defaults) so the user can tune behaviour without editing code.

    Attributes:
        auto: Enable automatic compaction when context is full.
        prune: Enable pruning of old tool outputs.
        tail_turns: Number of recent user turns to keep verbatim.
        preserve_recent_tokens: Max tokens from recent turns to preserve.
        reserved: Token buffer reserved for compaction.
        trigger_threshold: Fraction of context window that triggers
            compaction (overrides ``reserved`` if set).
        strategy: Compaction strategy name (``"original"``, ``"cod"``,
            or ``"ask"``).
        options: Strategies available when ``strategy == "ask"``.
    """

    auto: bool = True
    prune: bool = False
    tail_turns: int = 2
    preserve_recent_tokens: int = 0
    reserved: int = 20_000
    trigger_threshold: float = 0.8
    strategy: str = "original"
    options: list[str] = field(
        default_factory=lambda: ["cod", "original"]
    )

    @classmethod
    def from_env(cls) -> "CompactionConfig":
        """Build a config from environment variables.

        Reads the ``AGENT_COMPACTION_*`` variables: ``AUTO``, ``PRUNE``,
        ``TAIL_TURNS``, ``PRESERVE_RECENT_TOKENS``, ``RESERVED`` and
        ``TRIGGER_THRESHOLD``.

        Returns:
            The configuration.
        """
        strategy = os.getenv("AGENT_COMPACTION_STRATEGY", "original").strip()
        if strategy not in VALID_STRATEGIES:
            logger.warning(
                "Invalid AGENT_COMPACTION_STRATEGY=%r. Falling back to 'original'.",
                strategy,
            )
            strategy = "original"

        options_raw = os.getenv("AGENT_COMPACTION_OPTIONS", "cod,original").strip()
        options = [
            o.strip() for o in options_raw.split(",") if o.strip()
        ] or ["cod", "original"]

        return cls(
            auto=_to_bool(os.getenv("AGENT_COMPACTION_AUTO"), True),
            prune=_to_bool(os.getenv("AGENT_COMPACTION_PRUNE"), False),
            tail_turns=_to_int(os.getenv("AGENT_COMPACTION_TAIL_TURNS"), 2),
            preserve_recent_tokens=_to_int(
                os.getenv("AGENT_COMPACTION_PRESERVE_RECENT_TOKENS"), 0
            ),
            reserved=_to_int(os.getenv("AGENT_COMPACTION_RESERVED"), 20_000),
            trigger_threshold=_to_float(
                os.getenv("AGENT_COMPACTION_TRIGGER_THRESHOLD"), 0.8
            ),
            strategy=strategy,
            options=options,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict (useful for logging).

        Returns:
            The configuration as a dict.
        """
        return {
            "auto": self.auto,
            "prune": self.prune,
            "tail_turns": self.tail_turns,
            "preserve_recent_tokens": self.preserve_recent_tokens,
            "reserved": self.reserved,
            "trigger_threshold": self.trigger_threshold,
            "strategy": self.strategy,
            "options": list(self.options),
        }


@dataclass
class SessionContext:
    """Per-session context-window control.

    Attributes:
        context_limit: Optional max number of user/assistant message
            pairs to load from the session. ``None`` means no limit.
        max_context_tokens: Optional hard cap on token count. ``None``
            falls back to the model's default limit.
    """

    context_limit: int | None = None
    max_context_tokens: int | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> "SessionContext":
        """Build a SessionContext from session metadata.

        Expected keys (all optional):
        - ``context_limit`` (int)
        - ``max_context_tokens`` (int)

        Args:
            metadata: Metadata of the session, or None.

        Returns:
            The session context.
        """
        if not metadata:
            return cls()
        return cls(
            context_limit=metadata.get("context_limit"),
            max_context_tokens=metadata.get("max_context_tokens"),
        )

    def to_metadata(self) -> dict[str, Any]:
        """Convert to a dict suitable for storing in session metadata.

        Returns:
            The metadata dict.
        """
        data: dict[str, Any] = {}
        if self.context_limit is not None:
            data["context_limit"] = self.context_limit
        if self.max_context_tokens is not None:
            data["max_context_tokens"] = self.max_context_tokens
        return data


if __name__ == "__main__":
    cfg = CompactionConfig.from_env()
    print("CompactionConfig:")
    for k, v in cfg.to_dict().items():
        print(f"  {k}: {v}")
