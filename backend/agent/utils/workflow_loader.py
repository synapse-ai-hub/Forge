"""Load workflows and reusable agents from disk.

Layout::

    ~/.config/synapseForge/workflows/
        agent/                  # global reusable, fixed prompts editable by user
            router.md
            validator.md
        <nombre>/
            workflow.yaml
            agent/              # per-workflow override by same file name
                custom.md

The loader searches per-workflow ``agent/`` first, then global
``workflows/agent/``. Path traversal with ``..`` or ``/`` is rejected.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from backend.agent.permissions import _parse_frontmatter
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
    """List workflow names with a valid ``workflow.yaml``."""
    try:
        workflows_dir = get_workflows_dir()
        names: list[str] = []
        for entry in sorted(workflows_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith(".") and (entry / "workflow.yaml").is_file():
                names.append(entry.name)
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
        target = os.path.realpath(workflows_dir / name / "workflow.yaml")
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


def load_workflow_agent(workflow_name: str, agent_name: str) -> dict[str, Any]:
    """Load a reusable agent markdown with per-workflow override.

    Searches ``workflows/<workflow>/agent/<name>.md`` first, then
    ``workflows/agent/<name>.md``. Returns contract with frontmatter.
    """
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0}
    if not _safe_name(workflow_name) or not _safe_name(agent_name):
        return {"status": "error", "message": "Nombre de agente inválido.", "data": None, "usage": usage}
    try:
        workflows_dir = get_workflows_dir()
        base = os.path.realpath(workflows_dir)
        candidates = [
            workflows_dir / workflow_name / "agent" / f"{agent_name}.md",
            workflows_dir / "agent" / f"{agent_name}.md",
        ]
        for candidate in candidates:
            target = os.path.realpath(candidate)
            if not target.startswith(base + os.sep):
                continue
            md_path = Path(target)
            if md_path.is_file():
                with open(md_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                frontmatter = _parse_frontmatter(content)
                return {
                    "status": "success",
                    "message": "Agente cargado.",
                    "data": {"frontmatter": frontmatter, "content": content, "path": target},
                    "usage": usage,
                }
        return {"status": "error", "message": f"Agente '{agent_name}' no encontrado.", "data": None, "usage": usage}
    except Exception as exc:
        log_error(str(exc), source="workflow_loader.py:load_workflow_agent")
        return {"status": "error", "message": f"Error cargando agente '{agent_name}'.", "data": None, "usage": usage}
