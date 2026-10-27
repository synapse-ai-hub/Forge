"""Load workflows from disk.

Layout (flat, like GitHub Actions)::

    ~/.config/synapseForge/workflows/
        prompts/              # user prompts of the agent nodes (<nombre>.toml)
        <nombre>.yaml         # one flat file per flow

The loader reads ``*.yaml`` workflows and, through :func:`load_prompt_file`,
the ``*.toml`` prompt an ``agent`` node points to with ``prompt_file``. Path
traversal with ``..`` or ``/`` is rejected.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from backend.agent.utils.config_dir import get_workflow_prompts_dir, get_workflows_dir
from backend.agent.utils.error_logger import log_error
from backend.agent.utils.workflow_validator import validate_workflow

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _safe_name(name: str) -> bool:
    """Check that a workflow or agent name does not allow path traversal.

    Args:
        name: Name to check.

    Returns:
        ``True`` when the name is lowercase letters, numbers, ``_`` and ``-`` only.
    """
    if not name or not _NAME_RE.match(name):
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return True


def list_workflows() -> list[str]:
    """List workflow names from flat ``<name>.yaml`` files.

    Returns:
        The names of the workflows, sorted.
    """
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
    """Load and validate a workflow by name with realpath containment.

    Args:
        name: Workflow name.

    Returns:
        Contract dict ``{status, message, data, usage}``; ``data`` holds the normalized workflow.
    """
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


def list_scheduled() -> list[dict[str, Any]]:
    """List the workflows that have a ``schedule`` block (the scheduled tasks).

    Returns:
        One dict per scheduled workflow with ``name``, ``description`` and ``schedule``
        (see :func:`~backend.agent.utils.workflow_validator.normalize_schedule`);
        the invalid workflows are left out.
    """
    scheduled: list[dict[str, Any]] = []
    for name in list_workflows():
        loaded = load_workflow(name)
        if loaded.get("status") != "success":
            continue
        data = loaded["data"]
        if data.get("schedule"):
            scheduled.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "schedule": data["schedule"],
            })
    return scheduled


def save_schedule(name: str, schedule: dict[str, Any] | None) -> dict[str, Any]:
    """Write the ``schedule`` block of a workflow file (``None`` removes it).

    The rest of the file is kept; the YAML is written again, so its comments are lost.

    Args:
        name: Workflow name.
        schedule: Validated schedule (``{"enabled", "slots"}``), or ``None`` to remove it.

    Returns:
        Contract dict ``{status, message}``.
    """
    if not _safe_name(name):
        return {"status": "error", "message": f"Workflow '{name}' inválido."}
    try:
        workflows_dir = get_workflows_dir()
        base = os.path.realpath(workflows_dir)
        target = os.path.realpath(workflows_dir / f"{name}.yaml")
        if not target.startswith(base + os.sep):
            return {"status": "error", "message": "Ruta de workflow no permitida."}
        path = Path(target)
        if not path.is_file():
            return {"status": "error", "message": f"Workflow '{name}' no existe."}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"status": "error", "message": f"Workflow '{name}' inválido."}
        if schedule is None:
            data.pop("schedule", None)
        else:
            data["schedule"] = schedule
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        return {"status": "success", "message": "Horario guardado."}
    except Exception as exc:
        log_error(str(exc), source="workflow_loader.py:save_schedule")
        return {"status": "error", "message": f"No se pudo guardar el horario de '{name}'."}


def _render_toml(value: Any, level: int) -> str:
    """Render a parsed TOML value as readable text (tables become sections).

    Args:
        value: Parsed TOML value (table, list or scalar).
        level: Markdown heading level of the keys of a table.

    Returns:
        The text of the value.
    """
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{'#' * min(level, 6)} {key}\n\n{_render_toml(item, level + 1)}")
        return "\n\n".join(parts)
    if isinstance(value, list):
        return "\n".join(
            f"- {_render_toml(item, level + 1)}" if not isinstance(item, (dict, list)) else _render_toml(item, level + 1)
            for item in value
        )
    return str(value).strip()


def load_prompt_file(name: str) -> dict[str, Any]:
    """Load the user prompt of an ``agent`` node from ``workflows/prompts/<name>.toml``.

    The structure of the TOML is free (the workflow creator decides it): each
    key becomes a section of the message, tables nest. The text is the user
    message of the agent; its system prompt comes from its own markdown.

    Args:
        name: File name without extension (``prompt_file`` of the node).

    Returns:
        Contract dict. On success ``data`` is the prompt text.
    """
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0}
    if not name or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", name):
        return {"status": "error", "message": f"Nombre de prompt '{name}' inválido.", "data": None, "usage": usage}
    try:
        prompts_dir = get_workflow_prompts_dir()
        base = os.path.realpath(prompts_dir)
        target = os.path.realpath(prompts_dir / f"{name}.toml")
        if not target.startswith(base + os.sep):
            return {"status": "error", "message": "Ruta de prompt no permitida.", "data": None, "usage": usage}
        if not os.path.isfile(target):
            return {"status": "error", "message": f"No existe el prompt '{name}.toml' en la carpeta de prompts de workflows.", "data": None, "usage": usage}
        with open(target, "rb") as fh:
            data = tomllib.load(fh)
        text = _render_toml(data, 2).strip()
        if not text:
            return {"status": "error", "message": f"El prompt '{name}.toml' está vacío.", "data": None, "usage": usage}
        return {"status": "success", "message": "Prompt cargado.", "data": text, "usage": usage}
    except tomllib.TOMLDecodeError as exc:
        return {"status": "error", "message": f"El prompt '{name}.toml' no es un TOML válido: {exc}", "data": None, "usage": usage}
    except Exception as exc:
        log_error(str(exc), source="workflow_loader.py:load_prompt_file")
        return {"status": "error", "message": f"Error cargando el prompt '{name}.toml'.", "data": None, "usage": usage}
