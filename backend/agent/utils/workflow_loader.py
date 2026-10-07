"""Load workflows from disk.

Layout (flat, like GitHub Actions)::

    ~/.config/synapseForge/workflows/
        prompts/              # shared prompts (md, toml, anything)
        <nombre>.yaml         # one flat file per flow

The loader only reads ``*.yaml`` files. Path traversal with ``..``
or ``/`` is rejected.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from backend.agent.utils.config_dir import get_workflows_dir
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.workflow_validator import validate_workflow

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _safe_name(name: str) -> bool:
    """Check workflow or agent names reject traversal."""
    if not name or not _NAME_RE.match(name):
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return True


def list_workflows() -> list[str]:
    """List workflow names from flat ``<nombre>.yaml`` files."""
    try:
        workflows_dir = get_workflows_dir()
        names: list[str] = []
        for entry in sorted(workflows_dir.iterdir()):
            if (
                entry.is_file()
                and entry.suffix == ".yaml"
                and not entry.name.startswith(".")
                and _safe_name(entry.stem)
            ):
                names.append(entry.stem)
        return names
    except Exception as exc:
        log_error(str(exc), source="workflow_loader.py:list_workflows")
        return []


def load_workflow(name: str) -> dict[str, Any]:
    """Load and validate a workflow by name with realpath containment."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0}
    if not _safe_name(name):
        return {"status": "error", "message": f"Workflow '{name}' inválido.", "data": None, "usage": usage}
    try:
        workflows_dir = get_workflows_dir()
        base = os.path.realpath(workflows_dir)
        target = os.path.realpath(workflows_dir / f"{name}.yaml")
        if not target.startswith(base + os.sep):
            return {"status": "error", "message": "Ruta de workflow no permitida.", "data": None, "usage": usage}
        yaml_path = Path(target)
        if not yaml_path.is_file():
            return {"status": "error", "message": f"Workflow '{name}' no existe.", "data": None, "usage": usage}
        with open(yaml_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return validate_workflow(data if isinstance(data, dict) else {})
    except Exception as exc:
        log_error(str(exc), source="workflow_loader.py:load_workflow")
        return {"status": "error", "message": f"Error cargando workflow '{name}'.", "data": None, "usage": usage}
