"""Locate Jinja prompt templates in the ``prompts/`` tree.

Prompts live grouped by scope (``prompts/router/``, ``prompts/includes/``,
...); names are unique across folders, so a bare ``{name}.jinja`` lookup
and ``{% include %}`` resolve without folder prefixes.
"""

from __future__ import annotations

import os

_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"
)


def prompt_searchpath() -> list[str]:
    """Search path for Jinja prompt templates (root plus every subfolder).

    Returns:
        The prompts root followed by every subfolder, sorted.
    """
    paths = [_PROMPTS_DIR]
    for root, dirs, _files in os.walk(_PROMPTS_DIR):
        for name in sorted(dirs):
            paths.append(os.path.join(root, name))
    return paths


def find_prompt_file(prompt_name: str) -> str | None:
    """Locate a prompt template file by bare name in the prompts tree.

    Args:
        prompt_name: Template name (without the ``.jinja`` extension).

    Returns:
        The full path of the first match, or ``None`` if not found.
    """
    target = f"{prompt_name}.jinja"
    for root, _dirs, files in os.walk(_PROMPTS_DIR):
        if target in files:
            return os.path.join(root, target)
    return None
