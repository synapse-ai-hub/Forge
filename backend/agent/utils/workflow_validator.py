"""YAML schema validation for deterministic workflows (DAGs).

User-friendly source of truth. Same ``step`` means parallel with barrier,
different ``step`` means sequential. No LangGraph dependency.
"""

from __future__ import annotations

import os
import re
from typing import Any

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_NODE_TYPES = ("agent", "tool", "rag", "run")
_ON_FAILURE = ("continue", "abort")
_RUN_TIMEOUT_MIN_MS = 1000
_RUN_TIMEOUT_MAX_MS = 300000
_RUN_TIMEOUT_DEFAULT_MS = 30000


def _valid_run_workdir(workdir: str) -> bool:
    """Check a run node workdir stays inside the process working directory.

    Rejects absolute paths (posix, Windows drive letters, ``~``) and
    traversal, then verifies with ``realpath`` containment.

    Args:
        workdir: Relative working directory from the YAML.

    Returns:
        ``True`` when it resolves inside the working directory.
    """
    try:
        if not isinstance(workdir, str) or not workdir.strip():
            return False
        clean = workdir.strip().replace("\\", "/")
        if not clean or clean.startswith("/") or clean.startswith("~"):
            return False
        if re.match(r"^[a-zA-Z]:", clean):
            return False
        if ".." in clean.split("/"):
            return False
        base = os.path.realpath(os.getcwd())
        full = os.path.realpath(os.path.join(base, clean))
        return os.path.commonpath([base, full]) == base
    except Exception:
        return False


def validate_workflow(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a parsed workflow YAML dict.

    Returns:
        Contract dict ``{status, message, data, usage}``. On success,
        ``data`` holds the normalized workflow.
    """
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0}
    if not isinstance(data, dict):
        return {"status": "error", "message": "El workflow debe ser un objeto YAML.", "data": None, "usage": usage}

    name = str(data.get("name", "")).strip()
    if not _NAME_RE.match(name):
        return {"status": "error", "message": "Campo 'name' inválido. Usá minúsculas, números, guiones.", "data": None, "usage": usage}

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return {"status": "error", "message": "El workflow debe tener al menos un nodo en 'nodes'.", "data": None, "usage": usage}

    retries_default = data.get("retries", 2)
    if not isinstance(retries_default, int) or retries_default < 0 or retries_default > 10:
        return {"status": "error", "message": "Campo 'retries' debe ser entero entre 0 y 10.", "data": None, "usage": usage}

    on_failure = str(data.get("on_failure", "continue")).strip()
    if on_failure not in _ON_FAILURE:
        return {"status": "error", "message": "Campo 'on_failure' debe ser 'continue' o 'abort'.", "data": None, "usage": usage}

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            return {"status": "error", "message": f"Nodo {i} inválido: debe ser un objeto.", "data": None, "usage": usage}
        nid = str(node.get("id", "")).strip()
        if not nid or nid in seen_ids:
            return {"status": "error", "message": f"Nodo {i} con 'id' vacío o duplicado.", "data": None, "usage": usage}
        seen_ids.add(nid)
        ntype = str(node.get("type", "")).strip()
        if ntype not in _NODE_TYPES:
            return {"status": "error", "message": f"Nodo '{nid}' con 'type' inválido. Usá agent, tool, rag o run.", "data": None, "usage": usage}
        step = node.get("step")
        if not isinstance(step, int) or step < 1:
            return {"status": "error", "message": f"Nodo '{nid}' con 'step' inválido. Debe ser entero desde 1.", "data": None, "usage": usage}
        nretries = node.get("retries", retries_default)
        if not isinstance(nretries, int) or nretries < 0 or nretries > 10:
            return {"status": "error", "message": f"Nodo '{nid}' con 'retries' inválido.", "data": None, "usage": usage}
        if ntype == "agent" and not _REF_RE.match(str(node.get("agent_name", "")).strip()):
            return {"status": "error", "message": f"Nodo '{nid}' tipo agent requiere 'agent_name' válido.", "data": None, "usage": usage}
        if ntype == "tool" and not _REF_RE.match(str(node.get("tool", "")).strip()):
            return {"status": "error", "message": f"Nodo '{nid}' tipo tool requiere 'tool' válido.", "data": None, "usage": usage}
        if ntype == "rag" and not _REF_RE.match(str(node.get("collection", "")).strip()):
            return {"status": "error", "message": f"Nodo '{nid}' tipo rag requiere 'collection' válida.", "data": None, "usage": usage}
        run_raw = node.get("run", "")
        run_cmd = run_raw.strip() if isinstance(run_raw, str) else ""
        if ntype == "run" and not run_cmd:
            return {"status": "error", "message": f"Nodo '{nid}' tipo run requiere 'run' con el comando.", "data": None, "usage": usage}
        run_timeout = node.get("timeout", _RUN_TIMEOUT_DEFAULT_MS)
        if ntype == "run":
            if isinstance(run_timeout, bool) or not isinstance(run_timeout, int):
                return {"status": "error", "message": f"Nodo '{nid}' con 'timeout' inválido. Entero en ms.", "data": None, "usage": usage}
            if run_timeout < _RUN_TIMEOUT_MIN_MS or run_timeout > _RUN_TIMEOUT_MAX_MS:
                return {"status": "error", "message": f"Nodo '{nid}' con 'timeout' fuera de rango (1000-300000 ms).", "data": None, "usage": usage}
        else:
            run_timeout = _RUN_TIMEOUT_DEFAULT_MS
        run_workdir = str(node.get("workdir", "") or "").strip()
        if ntype == "run" and run_workdir and not _valid_run_workdir(run_workdir):
            return {"status": "error", "message": f"Nodo '{nid}' con 'workdir' inválido. Relativo sin '..'.", "data": None, "usage": usage}
        if ntype != "run":
            run_workdir = ""
            run_cmd = ""
        normalized.append({
            "id": nid,
            "type": ntype,
            "step": step,
            "retries": nretries,
            "agent_name": str(node.get("agent_name", "")).strip(),
            "prompt": str(node.get("prompt", "")),
            "tool": str(node.get("tool", "")).strip(),
            "args": node.get("args") if isinstance(node.get("args"), dict) else {},
            "collection": str(node.get("collection", "")).strip(),
            "query": str(node.get("query", "")),
            "run": run_cmd,
            "timeout": run_timeout,
            "workdir": run_workdir,
            "final": bool(node.get("final", False)),
        })

    normalized.sort(key=lambda n: (n["step"], n["id"]))
    steps = sorted({n["step"] for n in normalized})
    if steps != list(range(1, len(steps) + 1)):
        return {"status": "error", "message": "Los 'step' deben ser contiguos desde 1 sin huecos.", "data": None, "usage": usage}
    finals = [n for n in normalized if n["final"]]
    if len(finals) != 1:
        return {"status": "error", "message": "El workflow debe tener exactamente un nodo con 'final: true'.", "data": None, "usage": usage}
    return {
        "status": "success",
        "message": "Workflow válido.",
        "data": {
            "name": name,
            "description": str(data.get("description", "")),
            "version": str(data.get("version", "1")),
            "retries": retries_default,
            "on_failure": on_failure,
            "nodes": normalized,
        },
        "usage": usage,
    }
