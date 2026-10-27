"""Inventory of prompt templates against their call sites in the codebase.

Compares the ``agent.prompt("<name>", ...)`` calls found in ``backend/``
with the ``*.jinja`` files under ``backend/agent/prompts/`` and reports
names that are called but have no template (they would raise
``FileNotFoundError`` at runtime) and templates that nothing calls.
"""

from __future__ import annotations

import pathlib
import re

_CALL_RE = re.compile(r"\.prompt\(\s*[\"']([a-z_0-9]+)[\"']")


def prompt_call_sites(backend_dir: pathlib.Path | str) -> set[str]:
    """Collect every prompt name used in ``agent.prompt("<name>", ...)`` calls.

    Args:
        backend_dir: Path to the ``backend/`` directory to scan.

    Returns:
        The set of prompt names referenced in ``*.py`` files.
    """
    names: set[str] = set()
    try:
        files = list(pathlib.Path(backend_dir).rglob("*.py"))
    except OSError:
        return names
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        names.update(_CALL_RE.findall(text))
    return names


def prompt_templates(prompts_dir: pathlib.Path | str) -> set[str]:
    """Collect every prompt template name available on disk.

    Args:
        prompts_dir: Path to the ``backend/agent/prompts/`` directory.

    Returns:
        The set of template stems (without the ``.jinja`` extension).
    """
    try:
        return {p.stem for p in pathlib.Path(prompts_dir).rglob("*.jinja")}
    except OSError:
        return set()


def check_prompt_coverage(
    backend_dir: pathlib.Path | str,
    prompts_dir: pathlib.Path | str,
) -> dict[str, list[str]]:
    """Compare prompt call sites with the templates on disk.

    Args:
        backend_dir: Path to the ``backend/`` directory to scan.
        prompts_dir: Path to the ``backend/agent/prompts/`` directory.

    Returns:
        A dict with ``missing`` (called but without template) and
        ``unused`` (template without callers), both sorted.
    """
    calls = prompt_call_sites(backend_dir)
    templates = prompt_templates(prompts_dir)
    return {
        "missing": sorted(calls - templates),
        "unused": sorted(templates - calls),
    }
