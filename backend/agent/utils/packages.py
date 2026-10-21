"""Third-party libraries for the tools: one controlled way to install them.

The tools run inside the backend process, so a library they need is installed
in the Python that runs the backend (``sys.executable``): the venv created by
``init`` locally, the image's Python in Docker. Everything goes through
:func:`install_package`:

- always ``<sys.executable> -m pip install``, never a ``pip`` found in PATH;
- the packages of the project's ``requirements.txt`` are held at the version
  they have now (``-c``), so a tool's library can never change what the
  backend runs on: if it needs that, the install fails;
- the package is recorded in ``tools/lib/requirements.txt`` (config dir) and,
  when it exists and is writable, in the project's ``requirements.txt``;
- at startup :func:`restore_missing` reinstalls what that file lists and is
  missing (new machine, recreated container).
"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from backend.agent.utils.config_dir import get_tools_dir
from backend.agent.utils.contract import make_error_response, make_success_response, zero_usage
from backend.agent.utils.error_logger import log_error

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 600

_OP = r"(?:==|>=|<=|~=|!=|>|<)"
_VERSION = r"[A-Za-z0-9.*+!_-]+"
_SPEC_RE = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9,._-]+\])?(?:{_OP}{_VERSION}(?:,{_OP}{_VERSION})*)?$"
)
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")

_PIP_INSTALL_RE = re.compile(r"""(?:-m\s+pip3?|\bpip3?(?:\.exe)?)["']?\s+install\b""", re.IGNORECASE)
_PIP_PREFIX_RE = re.compile(
    r"""^(?:(?:\S*[\\/])?(?:python3?|py)(?:\.exe)?(?:\s+-\d(?:\.\d+)?)?\s+-m\s+pip3?|(?:\S*[\\/])?pip3?(?:\.exe)?)$""",
    re.IGNORECASE,
)
_SHELL_OPERATORS = {"&&", "||", "|", ";", "&", ">", ">>", "<", "2>&1"}
_ALLOWED_FLAGS = {"-q", "--quiet", "-U", "--upgrade", "--no-cache-dir", "--disable-pip-version-check"}

_REPO_HEADER = "# Installed by tools"


# ---------------------------------------------------------------------------
# Paths and names
# ---------------------------------------------------------------------------


def project_requirements_file() -> Path | None:
    """Locate the ``requirements.txt`` of the project.

    Returns:
        Its path, or ``None`` when it does not exist.
    """
    candidate = Path(__file__).resolve().parents[3] / "requirements.txt"
    return candidate if candidate.is_file() else None


def tools_requirements_file() -> Path:
    """Locate the persistent list of the libraries the tools installed.

    Returns:
        Path of ``tools/lib/requirements.txt`` in the config directory.
    """
    return get_tools_dir() / "lib" / "requirements.txt"


def _normalize(name: str) -> str:
    """Convert a distribution name to its canonical form.

    Args:
        name: Distribution name.

    Returns:
        The name in lowercase with ``-`` as the only separator.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(line: str) -> str | None:
    """Extract the distribution name of a requirements line.

    Args:
        line: Line of a requirements file.

    Returns:
        The name, or ``None`` for blank lines, comments and options.
    """
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    match = _NAME_RE.match(line)
    return match.group(0) if match else None


def _installed_version(name: str) -> str | None:
    """Look up the installed version of a distribution.

    Args:
        name: Distribution name.

    Returns:
        The version, or ``None`` when it is not installed.
    """
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _read_lines(path: Path) -> list[str]:
    """Read the lines of a text file.

    Args:
        path: File to read.

    Returns:
        Its lines, or an empty list when it cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def is_valid_spec(spec: str) -> bool:
    """Check that a requirement is plain: ``name``, ``name==1.2`` or ``name[extra]>=1``.

    URLs, paths, VCS references and pip options are rejected.

    Args:
        spec: Requirement to check.

    Returns:
        ``True`` when it is a plain requirement.
    """
    return isinstance(spec, str) and bool(_SPEC_RE.match(spec.strip()))


def _write_constraints() -> str | None:
    """Write a constraints file that holds the project's packages at their installed version.

    Returns:
        The path of the temporary file, or ``None`` when there is nothing to hold.
    """
    req = project_requirements_file()
    if req is None:
        return None
    pins: list[str] = []
    for line in _read_lines(req):
        name = _requirement_name(line)
        version = _installed_version(name) if name else None
        if name and version:
            pins.append(f"{name}=={version}")
    if not pins:
        return None
    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    with handle:
        handle.write("\n".join(pins) + "\n")
    return handle.name


def _run_pip(specs: list[str], extra: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run ``python -m pip install`` with the project's packages held.

    Args:
        specs: Requirements to install.
        extra: Additional pip options.

    Returns:
        The finished process.
    """
    constraints = _write_constraints()
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *(extra or [])]
    if constraints:
        cmd += ["-c", constraints]
    cmd += specs
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    finally:
        if constraints:
            try:
                os.unlink(constraints)
            except OSError:
                pass


def _record(name: str) -> None:
    """Record an installed library in the tools list and in the project's requirements.

    Args:
        name: Distribution name that was installed.
    """
    version = _installed_version(name)
    if version is None:
        return
    line = f"{name}=={version}"
    key = _normalize(name)

    tools_file = tools_requirements_file()
    try:
        tools_file.parent.mkdir(parents=True, exist_ok=True)
        kept = [ln for ln in _read_lines(tools_file) if _normalize(_requirement_name(ln) or "") != key]
        tools_file.write_text("\n".join([*kept, line]) + "\n", encoding="utf-8")
    except OSError as exc:
        log_error(str(exc), source="packages.py:record(tools)")

    repo_file = project_requirements_file()
    if repo_file is None:
        return
    lines = _read_lines(repo_file)
    if any(_normalize(_requirement_name(ln) or "") == key for ln in lines):
        return
    try:
        if _REPO_HEADER not in lines:
            lines += ["", _REPO_HEADER]
        lines.append(line)
        repo_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        # Read-only image or deployment: the tools list still has it.
        logger.info("requirements.txt del proyecto no escribible: %s", exc)


def install_package(spec: str) -> dict[str, Any]:
    """Install one library for the tools in the backend's Python and record it.

    Args:
        spec: Plain requirement (``trafilatura`` or ``trafilatura==2.0.0``).

    Returns:
        Contract dict. ``data`` has ``output`` (pip's output) and ``returncode``.
    """
    spec = (spec or "").strip()
    if not is_valid_spec(spec):
        return make_error_response(
            message=f"'{spec}' no es un paquete válido. Usá solo el nombre, con versión opcional (nombre==1.2.3).",
            usage=zero_usage(),
        )
    try:
        result = _run_pip([spec])
    except subprocess.TimeoutExpired:
        return make_error_response(
            message=f"La instalación de '{spec}' superó los {INSTALL_TIMEOUT_SECONDS} segundos.",
            usage=zero_usage(),
        )
    except Exception as exc:
        log_error(str(exc), source="packages.py:install_package")
        return make_error_response(message=f"No se pudo instalar '{spec}': {exc}", usage=zero_usage())

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return make_error_response(
            message=f"No se pudo instalar '{spec}'. Si pide cambiar una librería del backend, no se instala: "
                    f"{output[-500:]}",
            usage=zero_usage(),
        )
    importlib.invalidate_caches()
    name = _requirement_name(spec) or spec
    _record(name)
    return make_success_response(
        message=f"'{spec}' instalado.",
        data={"output": output[-2000:], "returncode": 0, "package": name, "version": _installed_version(name)},
        usage=zero_usage(),
    )


def restore_missing() -> list[str]:
    """Reinstall the libraries of ``tools/lib/requirements.txt`` that are missing.

    Meant for startup: a new machine or a recreated container keeps its tools
    (they live in the config dir) but not the libraries they imported.

    Returns:
        The requirements that were missing and got installed.
    """
    missing = []
    for line in _read_lines(tools_requirements_file()):
        name = _requirement_name(line)
        spec = line.split("#", 1)[0].strip()
        if name and is_valid_spec(spec) and _installed_version(name) is None:
            missing.append(spec)
    if not missing:
        return []
    try:
        result = _run_pip(missing)
    except Exception as exc:
        log_error(str(exc), source="packages.py:restore_missing")
        return []
    if result.returncode != 0:
        log_error(
            f"No se pudieron reinstalar las librerías de las tools: {(result.stderr or '').strip()[-500:]}",
            source="packages.py:restore_missing",
        )
        return []
    importlib.invalidate_caches()
    return missing


# ---------------------------------------------------------------------------
# Shell integration
# ---------------------------------------------------------------------------


def parse_pip_install(command: str) -> tuple[list[str], str] | None:
    """Detect a ``pip install`` in a shell command.

    Args:
        command: Command line to inspect.

    Returns:
        ``None`` when the command has no ``pip install``. Otherwise
        ``(specs, error)``: ``specs`` are the packages to install and
        ``error`` is not empty when the command cannot be honoured (it is
        chained with something else, uses options other than plain
        packages, or a package is not a plain requirement).
    """
    if not _PIP_INSTALL_RE.search(command or ""):
        return None
    hint = " Usá un comando solo, con paquetes puntuales: python -m pip install nombre[==version]."
    try:
        tokens = [t.strip("\"'") for t in shlex.split(command, posix=os.name != "nt")]
    except ValueError:
        return [], "No se pudo interpretar el comando de instalación." + hint
    if any(tok in _SHELL_OPERATORS for tok in tokens):
        return [], "El comando de instalación no puede ir encadenado con otros." + hint
    try:
        idx = next(i for i, tok in enumerate(tokens) if tok.lower() == "install")
    except StopIteration:
        return [], "No se pudo interpretar el comando de instalación." + hint
    if not _PIP_PREFIX_RE.match(" ".join(tokens[:idx])):
        return [], "El comando de instalación no es un pip install directo." + hint
    specs: list[str] = []
    for tok in tokens[idx + 1:]:
        if tok.startswith("-"):
            if tok not in _ALLOWED_FLAGS:
                return [], f"La opción '{tok}' no está permitida: la instalación es controlada por el sistema." + hint
            continue
        if not is_valid_spec(tok):
            return [], f"'{tok}' no es un paquete válido." + hint
        specs.append(tok)
    if not specs:
        return [], "Falta indicar qué paquete instalar." + hint
    return specs, ""


def backend_python_env() -> dict[str, str]:
    """Build the environment for shell commands.

    The folder of the backend's Python comes first in ``PATH``, so ``python
    script.py`` runs with the same interpreter (and libraries) as the backend.

    Returns:
        A copy of the environment variables.
    """
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env
