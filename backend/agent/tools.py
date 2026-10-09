"""Agent tools: native tools, external tools and MCP tools.

Defines the ``Tools`` class whose public methods are the **native tools**
(auto-discovered by introspection into the function-calling registry, all
following the unified response contract from ``contract.py``).

Tool sources:

- Native tools: public methods of this class (``read``, ``write``,
  ``websearch``, ``rag``, ``task``, ``search_memory``, ...).
- External tools: ``.py`` files in ``~/.config/synapseForge/tools/``,
  loaded dynamically by the registry.
- MCP tools: discovered from configured MCP servers via
  ``mcp_helper`` and wrapped as function schemas.

``tools_registry(tool_permissions)`` filters the combined registry with
the running agent's permissions (deny by default) before exposing it to
the LLM.
"""

import fnmatch
import glob as glob_module
import importlib
import importlib.util
import inspect
import types
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
import uuid
import html2text
from ddgs import DDGS
import imaplib
import smtplib
import asyncio
import time
import httpx
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

    
from backend.agent.permissions import (
    filter_tools,
    get_agent_prompt,
    get_skill_permissions,
    get_tool_permissions,
    get_agent_parameters
)
from backend.agent.utils.mcp_helper import (
    execute_mcp_tool,
    get_mcp_tools,
    is_mcp_tool,
    mcp_servers_configured,
    mcp_tools_discovered,
)
from backend.agent.utils.skill_loader import format_skills_section, find_skill_folder, parse_skill_md
from backend.agent.utils.email_parser import parse_email, parse_relative_date, is_older_than

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.agent.utils.contract import (
    make_error_response,
    make_success_response,
    zero_usage,
)
from backend.agent.utils.error_logger import log_error


logger = logging.getLogger(__name__)


class Tools:
    """Tools for the quotation agent.

    Each method implements a step of the quotation pipeline and
    returns a dictionary with the unified contract ``{status, message, data, usage}``.

    The ``registry`` property automatically exposes LLM-callable tools by scanning
    the class for public methods (no leading underscore). For each method it derives:

    * ``name`` — the method name
    * ``description`` — the first line of the docstring
    * ``parameters`` — JSON Schema inferred from the method signature (type hints + defaults)
    """

    _PY_TYPE_TO_JSON: dict = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
        type(None): "null",
    }

    @staticmethod
    def _param_to_schema(param: inspect.Parameter) -> dict | None:
        """Converts a single ``inspect.Parameter`` to a JSON Schema property dict.

        Uses the type annotation to select the JSON type and unwraps ``Optional`` /
        ``Union[..., None]`` so that ``str | None`` yields ``{"type": "string"}``.

        Args:
            param: The parameter to convert.

        Returns:
            A JSON Schema property dict, or ``None`` if the annotation is ``inspect.Parameter.empty``.
        """
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            return None

        # Unwrap Optional / Union[..., None] -> keep the non-None types
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())

        if origin is not None and origin.__name__ in ("Union", "Optional"):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                annotation = non_none[0]
            elif len(non_none) > 1:
                annotation = non_none[0]  # fallback: use first non-None

        # Handle types.UnionType (PEP 604 syntax: str | None)
        # These have __args__ but no __origin__
        if isinstance(annotation, types.UnionType):
            non_none = [a for a in annotation.__args__ if a is not type(None)]
            if len(non_none) == 1:
                annotation = non_none[0]
            elif len(non_none) > 1:
                annotation = non_none[0]  # fallback: use first non-None

        json_type = Tools._PY_TYPE_TO_JSON.get(annotation)
        if json_type is None:
            return None

        return {"type": json_type}

    def __init__(self):
        """Initializes Tools.
        
        """
        self._external_tools: list[dict] = self._scan_external_tools()
        self._tools_registry: list[dict] = self._build_tools_registry()
        # Effective tool permissions of the agent currently running (set by
        # the loop at the start of every run() and restored after each
        # sub-agent). Used by execute_tool for deny-by-default enforcement.
        self._current_tool_permissions: dict = {}

    # --- Tool registry ----------------------------------------

    def tools_registry(self, tool_permissions: dict | None = None) -> list[dict]:
        """Tools available for LLM function calling.

        When *tool_permissions* is ``None`` or empty, no tools are returned
        (deny by default). When a dict is provided (resolved from an agent's
        frontmatter via ``get_tool_permissions``) only the allowed tools are
        kept.

        Args:
            tool_permissions: Top-level permission dict from the agent
                frontmatter.

        Returns:
            List of tool schemas in API format.
        """
        # Self-heal: if MCP servers are configured but the registry holds no
        # MCP tool (e.g. a transient failure at startup), re-discover once so
        # the agent sees the MCP tools instead of an empty registry. A
        # cooldown prevents hammering the MCP server if it stays unreachable.
        if mcp_servers_configured() and not self._has_mcp_tools():
            now = time.time()
            if now - getattr(self, "_last_mcp_selfheal", 0.0) > 30.0:
                self._last_mcp_selfheal = now
                try:
                    self._tools_registry = self._build_tools_registry()
                except Exception as e:
                    # Keep the previous registry on failure; never crash the
                    # agent loop over a re-discovery attempt.
                    logging.getLogger(__name__).exception(
                        "tools_registry: MCP self-heal rebuild failed: %s", e
                    )
                    log_error(str(e), source="tools.py:tools_registry(self-heal)")
        return filter_tools(self._tools_registry, tool_permissions)

    def _has_mcp_tools(self) -> bool:
        """Return ``True`` if the current registry contains MCP tools.

        Checks the registry content (not the discovery mapping) so a late
        background discovery that populated the mapping but not the registry
        still triggers the self-heal.

        Returns:
            ``True`` when at least one registry tool is MCP-managed.
        """
        return any(
            is_mcp_tool(str(tool.get("function", {}).get("name", "")))
            for tool in self._tools_registry
        )

    def _build_tool_schema(
        self,
        name: str,
        description: str,
        sig: inspect.Signature,
        doc: str,
        skip_params: tuple[str, ...] = ("self",),
    ) -> dict | None:
        """Build a single tool schema entry from its metadata.

        Args:
            name: Tool/method name.
            description: Short description (first line of docstring).
            sig: Function signature.
            doc: Full docstring (used to extract parameter descriptions).
            skip_params: Parameter names to exclude (e.g. ``self``, ``agent``).

        Returns:
            ``{"type": "function", "function": {name, description, parameters}}``
            or ``None`` if no valid parameters remain.
        """
        param_descs = self._parse_param_descriptions(doc)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in skip_params:
                continue
            schema = self._param_to_schema(param)
            if schema is not None:
                pdesc = param_descs.get(param_name)
                if pdesc:
                    schema["description"] = pdesc
                properties[param_name] = schema
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def _build_tools_registry(self) -> list[dict]:
        """Build the function-calling schema list from all tool sources.

        Collects native methods (from ``Tools``) and external tools (from the
        ``tools/`` folder), then processes them all with ``_build_tool_schema``.

        Returns:
            List of tool definitions in API format.
        """
        # --- Collect all tool entries -----------------------------------------
        entries: list[tuple[str, str, inspect.Signature, str, tuple]] = []

        # Native methods (exclude private ones and tools_registry)
        for attr_name in dir(self):
            if attr_name.startswith("_") or attr_name == "tools_registry":
                continue
            method = getattr(self, attr_name, None)
            if not callable(method):
                continue

            doc = (method.__doc__ or "").strip()
            first_line = doc.split("\n")[0] if doc else ""
            if not first_line:
                continue

            try:
                sig = inspect.signature(method)
            except (ValueError, TypeError) as e:
                log_error(str(e), source="tools.py:_scan_external_tools(sig)")
                continue

            entries.append((attr_name, first_line, sig, doc, ("self",)))

        # External tools
        for ext in self._external_tools:
            fn = ext.get("fn")
            if not callable(fn):
                continue
            try:
                sig = inspect.signature(fn)
            except (ValueError, TypeError) as e:
                log_error(str(e), source="tools.py:_scan_external_tools(ext_sig)")
                continue

            entries.append((
                ext["name"],
                ext["description"],
                sig,
                (fn.__doc__ or ""),
                ("tools", "self"),
            ))

        # --- Process all entries with a single helper -------------------------
        tools: list[dict] = []
        for tup in entries:
            schema = self._build_tool_schema(*tup)
            if schema is not None:
                tools.append(schema)

        # --- MCP tools (wrapped as function schemas) --------------------------
        mcp_tools = get_mcp_tools()
        if mcp_tools:
            logger.info("Appending %d MCP tool(s) to registry", len(mcp_tools))
            tools.extend(mcp_tools)

        return tools

    @staticmethod
    def _parse_param_descriptions(doc: str) -> dict[str, str]:
        """Parse Google-style ``Args:`` section from a docstring.

        Looks for a block like::

            Args:
                param_name: Description text.
                other_param: Another description.

        Returns:
            ``{param_name: description}`` dict.
        """
        descs: dict[str, str] = {}
        if not doc:
            return descs

        lines = doc.split("\n")
        in_args = False
        for line in lines:
            stripped = line.strip()
            if stripped == "Args:":
                in_args = True
                continue
            if in_args:
                # Stop at the next section header (e.g. ``Returns:``, ``Raises:``)
                if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                    if stripped.endswith(":"):
                        break
                # Match ``param_name: description`` (indented)
                match = re.match(r"^(\w+):\s*(.*)", stripped)
                if match:
                    descs[match.group(1)] = match.group(2).strip()
        return descs

    

    # ------------------------------------------------------------------
    # External tool discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _locate_tools_dir() -> str | None:
        """Locate the external ``tools/`` folder.

        Uses the config directory ``~/.config/synapseForge/tools/``.
        Returns ``None`` (no error) if the folder does not exist.
        """
        from backend.agent.utils.config_dir import get_tools_dir

        tools_dir = get_tools_dir()
        if tools_dir.is_dir():
            return str(tools_dir)
        return None

    def _scan_external_tools(self) -> list[dict]:
        """Scan the external ``tools/`` folder for ``.py`` tool files.

        Each ``.py`` file directly in the folder (not subdirectories) is a
        standalone tool. Returns the loaded module and handler function
        so that ``_build_tools_registry`` can process them with the same
        schema builder used for native tools.

        Returns:
            List of ``{"name": str, "description": str, "fn": callable,
            "_module_path": str, "_handler_name": str}``.
        """
        tools_dir = self._locate_tools_dir()
        if not tools_dir:
            return []

        results: list[dict] = []
        for entry in sorted(os.listdir(tools_dir)):
            if not entry.endswith(".py") or entry.startswith("__"):
                continue

            module_name = entry[:-3]
            module_path = os.path.join(tools_dir, entry)

            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                _added = False
                if tools_dir not in sys.path:
                    sys.path.insert(0, tools_dir)
                    _added = True
                try:
                    spec.loader.exec_module(mod)
                finally:
                    if _added:
                        sys.path.remove(tools_dir)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to load external tool '%s': %s", module_name, e
                )
                log_error(str(e), source="tools.py:_scan_external_tools")
                continue

            # Module-level docstring first line → description
            mod_doc = (mod.__doc__ or "").strip()
            description = mod_doc.split("\n")[0] if mod_doc else ""
            if not description:
                continue

            # Function must have same name as the module
            fn = getattr(mod, module_name, None)
            if not callable(fn):
                continue

            results.append({
                "name": module_name,
                "description": description,
                "fn": fn,
                "_module_path": module_path,
                "_handler_name": module_name,
            })

        return results

    # ------------------------------------------------------------------
    # Tool executor — dispatches to native or external handlers
    # ------------------------------------------------------------------

    async def _execute_tool(self, tool_name: str, **kwargs) -> dict:
        """Execute a tool by name, dispatching to native or external handler.

        Args:
            tool_name: Tool name (method name or external file name).
            **kwargs: Parameters to pass to the tool.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        # External tools have priority (override native)
        for ext in self._external_tools:
            if ext["name"] == tool_name:
                module_path = ext["_module_path"]
                handler_name = ext["_handler_name"]
                try:
                    spec = importlib.util.spec_from_file_location(tool_name, module_path)
                    if spec is None or spec.loader is None:
                        return make_error_response(
                            message=f"execute_tool: no se pudo cargar '{tool_name}'",
                            usage=zero_usage(),
                        )
                    mod = importlib.util.module_from_spec(spec)
                    # Temporarily add tools_dir to sys.path for sibling/lib imports
                    tools_dir = self._locate_tools_dir()
                    _added = False
                    if tools_dir and tools_dir not in sys.path:
                        sys.path.insert(0, tools_dir)
                        _added = True
                    try:
                        spec.loader.exec_module(mod)
                    finally:
                        if _added:
                            sys.path.remove(tools_dir)
                    handler = getattr(mod, handler_name, None)
                    if handler is None:
                        return make_error_response(
                            message=f"execute_tool: '{tool_name}' no expone handler '{handler_name}'",
                            usage=zero_usage(),
                        )
                    # External tools are self-contained — pass only user params
                    return await handler(**kwargs)
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "execute_tool: error en '%s': %s", tool_name, e
                    )
                    log_error(str(e), source="tools.py:execute_tool")
                    return make_error_response(
                        message=f"execute_tool: error en '{tool_name}': {e}",
                        usage=zero_usage(),
                    )

        # Fall back to native method
        native = getattr(self, tool_name, None)
        if native and callable(native):
            return await native(**kwargs)

        # --- MCP tool dispatch -----------------------------------------------
        # Attempt MCP dispatch when the tool is known MCP, or when MCP servers
        # are configured but nothing was discovered yet (let execute_mcp_tool's
        # one-shot self-heal re-discover before giving up).
        if is_mcp_tool(tool_name) or (
            mcp_servers_configured() and not mcp_tools_discovered()
        ):
            try:
                mcp_result = await execute_mcp_tool(tool_name, kwargs)
                return make_success_response(
                    message=f"MCP tool '{tool_name}' ejecutado.",
                    data=mcp_result,
                    usage=zero_usage(),
                )
            except Exception as e:
                logger.exception("MCP tool '%s' failed", tool_name)
                log_error(str(e), source="tools.py:_execute_tool")
                return make_error_response(
                    message=f"MCP tool '{tool_name}' error: {e}",
                    usage=zero_usage(),
                )

        return make_error_response(
            message=f"execute_tool: tool '{tool_name}' no encontrada en native, externas ni MCP",
            usage=zero_usage(),
        )

    # ------------------------------------------------------------------
    # Herramientas nativas — filesystem, web, shell
    # ------------------------------------------------------------------

    async def read(self, file_path: str, offset: int = 1, limit: int = 2000) -> dict:
        """Read a file or directory from the local filesystem.

        Args:
            file_path: The absolute path to the file or directory to read.
            offset: The line number to start reading from (1-indexed).
            limit: The maximum number of lines to read (defaults to 2000).

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            if not os.path.exists(file_path):
                parent = os.path.dirname(file_path)
                base = os.path.basename(file_path)
                if os.path.isdir(parent):
                    similares = [f for f in os.listdir(parent) if base.lower() in f.lower()]
                    if similares:
                        return make_error_response(
                            message=f"File not found: {file_path}. Did you mean: {similares[:3]}?",
                            usage=zero_usage(),
                        )
                return make_error_response(
                    message=f"File not found: {file_path}",
                    usage=zero_usage(),
                )

            if os.path.isdir(file_path):
                items = sorted(os.listdir(file_path))
                items = [
                    f"{i}/" if os.path.isdir(os.path.join(file_path, i)) else i
                    for i in items
                ]
                start = offset - 1
                sliced = items[start:start + limit]
                output = f"<path>{file_path}</path>\n<entries>\n"
                output += "\n".join(sliced) + "\n"
                if start + len(sliced) < len(items):
                    output += (
                        f"(Showing {len(sliced)} of {len(items)} entries. "
                        f"Use offset={offset + len(sliced)} to continue.)"
                    )
                else:
                    output += f"({len(items)} entries)"
                output += "\n</entries>"
                return make_success_response(
                    message="Directory listed successfully.",
                    data=output,
                    usage=zero_usage(),
                )

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if offset > len(lines):
                return make_error_response(
                    message=f"Offset {offset} is out of range ({len(lines)} lines).",
                    usage=zero_usage(),
                )

            selected = lines[offset - 1:offset - 1 + limit]
            output = f"<path>{file_path}</path>\n<type>file</type>\n<content>\n"
            output += "".join(f"{i + offset}: {line}" for i, line in enumerate(selected))

            last_line = offset + len(selected) - 1
            if offset + len(selected) <= len(lines):
                output += (
                    f"\n(Showing lines {offset}-{last_line} of {len(lines)}. "
                    f"Use offset={last_line + 1} to continue.)"
                )
            else:
                output += f"\n(End of file - total {len(lines)} lines)"
            output += "\n</content>"

            return make_success_response(
                message="File read successfully.",
                data=output,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in read: %s", e)
            log_error(str(e), source="tools.py:read")
            return make_error_response(
                message=f"Error reading file: {e}",
                usage=zero_usage(),
            )

    async def write(self, file_path: str, content: str) -> dict:
        """Writes content to a file on the local filesystem.

        Creates parent directories if they do not exist.

        Args:
            file_path: The absolute path to the file to write.
            content: The content to write to the file.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return make_success_response(
                message="Wrote file successfully.",
                data={"file_path": file_path},
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in write: %s", e)
            log_error(str(e), source="tools.py:write")
            return make_error_response(
                message=f"Error writing file: {e}",
                usage=zero_usage(),
            )

    async def edit(self, file_path: str, old_string: str, new_string: str,
                   replace_all: bool = False) -> dict:
        """Performs exact string replacements in a file.

        Args:
            file_path: The absolute path to the file to modify.
            old_string: The text to replace.
            new_string: The text to replace it with (must be different from old_string).
            replace_all: Replace all occurrences of old_string (default False).

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            if not os.path.exists(file_path):
                return make_error_response(
                    message=f"File not found: {file_path}",
                    usage=zero_usage(),
                )
            if old_string == new_string:
                return make_error_response(
                    message="old_string and new_string are identical.",
                    usage=zero_usage(),
                )

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if replace_all:
                if old_string not in content:
                    return make_error_response(
                        message=f"old_string not found in {file_path}",
                        usage=zero_usage(),
                    )
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                count = content.count(old_string)
                if count == 0:
                    return make_error_response(
                        message=f"old_string not found in {file_path}",
                        usage=zero_usage(),
                    )
                if count > 1:
                    return make_error_response(
                        message=f"Found {count} matches. Provide more context or use replace_all=True.",
                        usage=zero_usage(),
                    )
                new_content = content.replace(old_string, new_string)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return make_success_response(
                message=f"Edit applied successfully ({count} replacement(s)).",
                data={"file_path": file_path, "replacements": count},
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in edit: %s", e)
            log_error(str(e), source="tools.py:edit")
            return make_error_response(
                message=f"Error editing file: {e}",
                usage=zero_usage(),
            )

    async def glob(self, pattern: str, path: str | None = None) -> dict:
        """Fast file pattern matching tool.

        Supports glob patterns like ``**/*.js`` or ``src/**/*.ts``.

        Args:
            pattern: The glob pattern to match files against.
            path: The directory to search in. Defaults to current working directory.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            search = path or os.getcwd()
            if not os.path.isdir(search):
                return make_error_response(
                    message=f"The path must be a directory: {search}",
                    usage=zero_usage(),
                )

            files = glob_module.glob(pattern, root_dir=search, recursive=True)
            limit = 100
            results = [os.path.normpath(os.path.join(search, f)) for f in sorted(files)]

            if not results:
                return make_success_response(
                    message="No files found.",
                    data=[],
                    usage=zero_usage(),
                )

            output = "\n".join(results[:limit])
            if len(results) > limit:
                output += (
                    f"\n(Results are truncated: showing first {limit}. "
                    "Consider using a more specific pattern.)"
                )

            return make_success_response(
                message=f"{min(len(results), limit)} file(s) found.",
                data=output,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in glob: %s", e)
            log_error(str(e), source="tools.py:glob")
            return make_error_response(
                message=f"Error in glob: {e}",
                usage=zero_usage(),
            )

    async def grep(self, pattern: str, path: str | None = None,
                   include: str | None = None) -> dict:
        """Search file contents using regular expressions.

        Args:
            pattern: The regex pattern to search for in file contents.
            path: The directory to search in. Defaults to current working directory.
            include: File pattern to include (e.g. ``*.py``, ``*.{ts,tsx}``).

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            search = path or os.getcwd()
            results: list[str] = []

            for root, _dirs, files in os.walk(search):
                if include:
                    files = [f for f in files if fnmatch.fnmatch(f, include)]
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                            for i, line in enumerate(fh, 1):
                                if re.search(pattern, line):
                                    results.append(f"{fpath}:{i}: {line.rstrip()}")
                                    if len(results) >= 100:
                                        break
                    except (OSError, UnicodeDecodeError) as e:
                        log_error(str(e), source="tools.py:grep")
                        continue
                    if len(results) >= 100:
                        break
                if len(results) >= 100:
                    break

            if not results:
                return make_success_response(
                    message="No files found.",
                    data=[],
                    usage=zero_usage(),
                )

            output = "\n".join(results[:100])
            if len(results) > 100:
                output += (
                    f"\n(Results are truncated: {len(results)} matches found. "
                    "Consider using a more specific pattern.)"
                )

            return make_success_response(
                message=f"{len(results)} match(es) found.",
                data=output,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in grep: %s", e)
            log_error(str(e), source="tools.py:grep")
            return make_error_response(
                message=f"Error in grep: {e}",
                usage=zero_usage(),
            )

    async def webfetch(self, url: str, format: str = "markdown") -> dict:
        """Fetches content from a specified URL.

        Args:
            url: The URL to fetch. HTTP URLs will be upgraded to HTTPS.
            format: The return format. Options: ``"markdown"`` (default), ``"text"``, ``"html"``.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            url = url.replace("http://", "https://")
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                content = resp.text

            if format == "html":
                return make_success_response(
                    message="Content fetched successfully.",
                    data=content[:10000],
                    usage=zero_usage(),
                )
            if format == "text":
                text = re.sub(r"<[^>]+>", "", content)
                return make_success_response(
                    message="Content fetched successfully.",
                    data=text[:10000],
                    usage=zero_usage(),
                )

            # Markdown
            try:
                
                converter = html2text.HTML2Text()
                converter.body_width = 0
                md = converter.handle(content)[:10000]
                return make_success_response(
                    message="Content fetched successfully.",
                    data=md,
                    usage=zero_usage(),
                )
            except ImportError as e:
                log_error(str(e), source="tools.py:webfetch(html2text)")
                # Fallback: strip tags
                text = re.sub(r"<[^>]+>", "", content)
                return make_success_response(
                    message="Content fetched successfully (html2text not available, using text fallback).",
                    data=text[:10000],
                    usage=zero_usage(),
                )
        except Exception as e:
            logger.exception("Error in webfetch: %s", e)
            log_error(str(e), source="tools.py:webfetch")
            return make_error_response(
                message=f"Error fetching URL: {e}",
                usage=zero_usage(),
            )

    async def websearch(self, query: str, num_results: int = 8) -> dict:
        """Search the web using the configured provider.

        Args:
            query: The search query string.
            num_results: Number of search results to return (default: 8).

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num_results))

            if not results:
                return make_success_response(
                    message="No results found.",
                    data=[],
                    usage=zero_usage(),
                )

            output = "\n".join(
                [f"{r['title']}: {r['href']}" for r in results]
            )
            return make_success_response(
                message=f"{len(results)} result(s) found.",
                data=output,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in websearch: %s", e)
            log_error(str(e), source="tools.py:websearch")
            return make_error_response(
                message=f"Error in websearch: {e}",
                usage=zero_usage(),
            )

    async def rag(self, collection: str, query: str) -> dict:
        """Query a knowledge base (RAG) collection.

        Finds the chunks most similar to the query inside the given
        collection and returns the results with their metadata. The agent can
        only query the collections allowed in its frontmatter
        (``permission.rag``), just like ``task`` restricts sub-agents.

        Args:
            collection: Name of the collection to query.
            query: Natural language query.

        Returns:
            dict with ``{status, message, data, usage}``. ``data`` contains
            the search results (ids, documents, metadatas, distances).
        """
        try:
            from backend.agent.utils.vector_db import get_vector_db

            if not query or not query.strip():
                return make_error_response(
                    message="La consulta no puede estar vacía.",
                    usage=zero_usage(),
                )

            # Shared instance (pre-loaded at app startup): the embedding model
            # and the Chroma client are loaded once and never killed.
            db = get_vector_db()

            try:
                db.get_collection(collection)
            except ValueError:
                return make_error_response(
                    message=f"La colección '{collection}' no existe.",
                    usage=zero_usage(),
                )

            _rag_t0 = time.time()
            results = db.query(collection, query, n_results=5)
            _rag_duration = round(time.time() - _rag_t0, 2)
            prompt_tokens = db.embed_func.count_tokens([query])
            # Track the query-embedding call in SQLite. Never breaks the flow.
            try:
                from backend.agent.utils.spend_handler import record_external_usage

                record_external_usage(
                    "embedding", "google", db.embed_func.model_name, 1,
                    duration=_rag_duration,
                    prompt_tokens=prompt_tokens,
                )
            except Exception:
                pass
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
                "total_time": _rag_duration,
            }
            return make_success_response(
                message=f"Resultados de '{collection}'.",
                data=results,
                usage=usage,
            )
        except Exception as e:
            logger.exception("Error in rag: %s", e)
            log_error(str(e), source="tools.py:rag")
            return make_error_response(
                message="Error consultando la colección.",
                usage=zero_usage(),
            )

    async def search_memory(self, query: str, limit: int = 5) -> dict:
        """Search the user's past conversations (long-term memory).

        Use it when the user asks about previous conversations or mentions
        information that is not in the current session.

        Queries the ``agent_conversations`` ChromaDB collection (indexed
        automatically at the end of every turn) and returns the most relevant
        fragments with their metadata (session, title, date, turn). The current
        session is always excluded from the results so it never searches
        itself.

        Args:
            query: Natural language query describing what to look for in past
                conversations.
            limit: Maximum number of results to return (default 5).

        Returns:
            dict with ``{status, message, data, usage}``. ``data`` contains a
            list of results with ``document``, ``session_id``,
            ``session_title``, ``turn_number``, ``date`` and ``distance``.
        """
        try:
            from backend.agent.utils.vector_db import get_vector_db
            from backend.agent.utils.rag_helpers import MEMORY_COLLECTION

            if not query or not query.strip():
                return make_error_response(
                    message="La consulta no puede estar vacía.",
                    usage=zero_usage(),
                )

            # Shared instance (pre-loaded at app startup): the embedding model
            # and the Chroma client are loaded once and never killed.
            db = get_vector_db()

            try:
                db.get_collection(MEMORY_COLLECTION)
            except ValueError:
                return make_success_response(
                    message="Todavía no hay conversaciones indexadas.",
                    data=[],
                    usage=zero_usage(),
                )

            # Exclude the current session so it never retrieves itself.
            current_session_id = getattr(self, "_current_session_id", None)
            where = (
                {"session_id": {"$ne": current_session_id}}
                if current_session_id
                else None
            )

            _mem_t0 = time.time()
            results = db.query(
                MEMORY_COLLECTION,
                query,
                n_results=max(1, int(limit)),
                where=where,
            )
            _mem_duration = round(time.time() - _mem_t0, 2)
            prompt_tokens = db.embed_func.count_tokens([query])
            # Track the query-embedding call in SQLite. Never breaks the flow.
            try:
                from backend.agent.utils.spend_handler import record_external_usage

                record_external_usage(
                    "embedding", "google", db.embed_func.model_name, 1,
                    duration=_mem_duration,
                    prompt_tokens=prompt_tokens,
                )
            except Exception:
                pass
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
                "total_time": _mem_duration,
            }

            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]

            formatted: list[dict] = []
            for doc, meta, dist in zip(documents, metadatas, distances):
                formatted.append({
                    "document": doc,
                    "session_id": (meta or {}).get("session_id", ""),
                    "session_title": (meta or {}).get("session_title", ""),
                    "turn_number": (meta or {}).get("turn_number"),
                    "date": (meta or {}).get("date", ""),
                    "distance": dist,
                })

            if not formatted:
                return make_success_response(
                    message="No se encontraron conversaciones relacionadas.",
                    data=[],
                    usage=usage,
                )

            return make_success_response(
                message=f"{len(formatted)} fragmento(s) encontrado(s) en conversaciones anteriores.",
                data=formatted,
                usage=usage,
            )
        except Exception as e:
            logger.exception("Error in search_memory: %s", e)
            log_error(str(e), source="tools.py:search_memory")
            return make_error_response(
                message="Error buscando en conversaciones anteriores.",
                usage=zero_usage(),
            )

    async def task(self, agent_name: str, prompt: str) -> dict:
        """Delegate work to a sub-agent.

        Resolves the sub-agent's system prompt and permissions from its
        markdown definition, creates an integrated child session
        (``parent_id``), runs the agent loop inside that session, and
        returns the final answer wrapped in an XML block.

        The *prompt* argument is the **user task** the calling agent wants
        the sub-agent to perform (generated by the caller). The sub-agent's
        **system prompt** (its role / behaviour) is resolved here from its
        markdown.

        Args:
            agent_name: Name of the sub-agent to delegate to.
            prompt: Detailed task description for the sub-agent (user message).

        Returns:
            dict with ``{status, message, data, usage}``. ``data`` is the XML
            result block consumed by the parent agent as a tool result.
        """

        # 1. Resolve sub-agent data from its markdown definition
        # Check if loop.py already resolved permissions (cached on tools instance)
        # A parallel-loop snapshot (ContextVar) carries this call's resolved
        # config, so concurrent task() calls never read each other's cache.
        # The shared ``_task_config`` attribute is only used as a legacy
        # fallback for callers outside the agent loop. Lazy import: top-level
        # would be circular (loop_helpers -> instances -> agent -> tools).
        from backend.agent.utils.loop_helpers import _tool_call_ctx

        snapshot_cfg = _tool_call_ctx.get()
        resolved_cfg = (
            snapshot_cfg.get("task_config")
            if snapshot_cfg is not None and "task_config" in snapshot_cfg
            else None
        )
        cached = resolved_cfg if resolved_cfg is not None else getattr(self, "_task_config", None)
        if cached and cached.get("agent_name") == agent_name:
            # Reuse cached values — avoids re-reading agent .md
            tool_perms = cached["tool_permissions"]
            skill_perms = cached["skill_permissions"]
            parameters = cached["parameters"]
            parent_model = cached.get("parent_model")
            parent_provider = cached.get("parent_provider")
            # Clear cache for next delegation
            self._task_config = None
        else:
            # First-time resolution (called outside loop.py). Fall back to the
            # agent singleton's globally-resolved model/provider as the parent
            # reference for the sub-agent.
            from backend.instances import agent as _agent_singleton
            parent_model = getattr(_agent_singleton, "_resolved_model", None)
            parent_provider = getattr(_agent_singleton, "provider", None)

            tool_perms: dict = {}
            tp = get_tool_permissions(agent_name)
            if tp.get("status") == "success":
                try:
                    tool_perms = json.loads(tp["data"])
                except (json.JSONDecodeError, TypeError) as e:
                    log_error(str(e), source="tools.py:task(tool_perms)")
                    tool_perms = {}

            skill_perms: dict = {}
            sp = get_skill_permissions(agent_name)
            if sp.get("status") == "success":
                try:
                    skill_perms = json.loads(sp["data"])
                except (json.JSONDecodeError, TypeError) as e:
                    log_error(str(e), source="tools.py:task(skill_perms)")
                    skill_perms = {}

            # Resolve model parameters from sub-agent frontmatter
            params_result = get_agent_parameters(agent_name)
            parameters: dict = {}
            if params_result.get("status") == "success":
                try:
                    parameters = json.loads(params_result.get("data", "{}"))
                except (json.JSONDecodeError, TypeError) as e:
                    log_error(str(e), source="tools.py:task(parameters)")

        # 1b. Resolve the sub-agent's system prompt via the shared builder

        # (build_system_prompt handles Behavior from AGENT.md, MANDATORY and
        # Fecha for sub-agents too). The agent existence is checked first so
        # a missing agent returns a user-friendly error instead of falling
        # back to the router prompt. Errors never raise: they are reported
        # as a user-friendly message to the front.
        prompt_result = get_agent_prompt(agent_name)
        if prompt_result.get("status") != "success":
            return make_error_response(
                message=f"No se encontró el agente '{agent_name}'. Revisá que exista en la carpeta de agentes.",
                usage=zero_usage(),
            )

        try:
            from backend.agent.utils.loop_helpers import build_system_prompt

            system_prompt = build_system_prompt(agent_name)
            # print(f'Agente: {agent_name}\n\nPrompt:\n{system_prompt}')
        except Exception as exc:
            log_error(str(exc), source="tools.py:task(system_prompt)")
            return make_error_response(
                message=f"No se pudo preparar el agente '{agent_name}'. Revisá su definición e intentá de nuevo.",
                usage=zero_usage(),
            )

        # 2. Create an integrated child session (parent_id = current session)
        from backend.instances import agent, session_manager

        # print(f'\n\n\n{"#"*80}\nSystem prompt:\n\n{system_prompt}\n{"#"*80}\n\n\n')

        # A parallel-loop snapshot (ContextVar) takes precedence over the
        # shared attributes, so concurrent task() calls cannot overwrite
        # each other's parent session, depth, cancel event or event queue.
        # Callers outside the agent loop leave it unset and the legacy
        # shared attributes are used, exactly as before.
        snapshot = _tool_call_ctx.get()
        if snapshot is not None:
            parent_id = snapshot.get("parent_session_id", getattr(self, "_current_session_id", None))
            depth = snapshot.get("depth", getattr(self, "_current_depth", 0))
            stream_cancel_event = snapshot.get(
                "stream_cancel_event", getattr(self, "_stream_cancel_event", None)
            )
            event_queue = snapshot.get(
                "subagent_event_queue", getattr(self, "_subagent_event_queue", None)
            )
        else:
            parent_id = getattr(self, "_current_session_id", None)
            depth = getattr(self, "_current_depth", 0)
            stream_cancel_event = getattr(self, "_stream_cancel_event", None)
            event_queue = getattr(self, "_subagent_event_queue", None)

        child_id = (
            f"{parent_id}:{agent_name}:{uuid.uuid4().hex[:8]}"
            if parent_id
            else f"{agent_name}:{uuid.uuid4().hex[:8]}"
        )
        create_res = session_manager.create_session(child_id, parent_id=parent_id)
        if create_res.get("status") != "success":
            return make_error_response(
                message=f"No se pudo crear la sub-sesión: {create_res.get('message')}",
                usage=zero_usage(),
            )

        # 3. Run the sub-agent loop inside the child session
        from backend.agent.loop import AgentLoop


        loop = AgentLoop(
            agent=agent,
            session_manager=session_manager,
        )
        final_text = ""
        state = "completed"
        if event_queue is not None:
            logger.info("task() has event_queue for child=%s", child_id[:8])
        else:
            logger.info("task() NO event_queue for child=%s", child_id[:8])
        try:

            async for sse in loop.run(
                session_id=child_id,
                user_message=prompt,
                system_prompt=system_prompt,
                tool_permissions=tool_perms,
                skill_permissions=skill_perms,
                parameters=parameters,
                agent_name=agent_name,
                depth=depth + 1,
                parent_id=parent_id,
                parent_model=parent_model,
                parent_provider=parent_provider,
                stream_cancel_event=stream_cancel_event,
            ):
                if sse.strip() == "data: [DONE]":
                    break
                if sse.startswith("data: "):
                    try:
                        payload = json.loads(sse[len("data: "):].strip())
                    except (json.JSONDecodeError, ValueError) as e:
                        log_error(str(e), source="tools.py:task(sse_parse)")
                        continue

                    # Forward sub-agent event to parent's SSE stream in real-time
                    if event_queue is not None:
                        sub_event = {
                            "type": "subagent_event",
                            "content": {
                                "child_session_id": child_id,
                                "agent_name": agent_name,
                                "event": payload,
                            },
                        }
                        await event_queue.put(sub_event)
                        if payload.get("type") in ("tool_call", "tool_result"):
                            logger.info(
                                ">> queued event type=%s child=%s",
                                payload.get("type"),
                                child_id[:8],
                            )

                    if payload.get("type") == "chunk":
                        final_text += payload.get("content", "")
        except Exception as exc:
            logger.exception("Error en sub-agente '%s': %s", agent_name, exc)
            log_error(str(exc), source="tools.py:task")
            final_text = "Ocurrió un error al ejecutar el sub-agente."
            state = "error"

        # 4. Return the result wrapped in XML (consumed by the parent as tool result)

        xml = (
            f'<task id="{child_id}" state="{state}">'
            f"<task_result>{final_text}</task_result>"
            f"</task>"
        )

        return make_success_response(
            message=f"Tarea delegada a '{agent_name}'.",
            data=xml,
            usage=zero_usage(),
        )

    
    async def shell(self, command: str, timeout: int = 30000,
                    workdir: str | None = None) -> dict:
        """Run a terminal command in the system shell.

        Non-blocking: runs the command in a worker thread (via
        ``asyncio.to_thread``) so the event loop keeps serving Telegram
        polling / SSE while the command executes. This avoids the
        ``NotImplementedError`` raised by ``asyncio.create_subprocess_shell``
        on Windows when the running event loop is a ``SelectorEventLoop``
        (which does not implement subprocess transport).

        Supports cancellation via the stream cancel event (the worker thread
        is abandoned; the process may keep running in the background) and a
        timeout. Output larger than 50 KB is truncated.

        Args:
            command: The command to execute (e.g. ``"dir"``, ``"python script.py"``).
            timeout: Maximum execution time in milliseconds (default 30000).
            workdir: Working directory for the command. If None, uses project root.

        Returns:
            dict with ``{status, message, data, usage}``.
            ``data`` contains ``output``, ``returncode``, and ``truncated``.
        """
        cancel_event = getattr(self, "_stream_cancel_event", None)
        try:
            cwd = workdir or os.getcwd()
            timeout_s = timeout / 1000

            # Run the blocking subprocess call in a worker thread so the
            # event loop is never blocked. ``subprocess.run`` works on every
            # platform regardless of the event-loop policy (unlike
            # ``asyncio.create_subprocess_shell`` which is unsupported on
            # Windows ``SelectorEventLoop``).
            def _run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )

            run_task = asyncio.create_task(asyncio.to_thread(_run))
            cancel_task = (
                asyncio.create_task(cancel_event.wait())
                if cancel_event is not None
                else None
            )

            tasks = [run_task]
            if cancel_task is not None:
                tasks.append(cancel_task)

            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            cancelled = cancel_task is not None and cancel_task in done

            if cancelled:
                for t in pending:
                    t.cancel()
                # The worker thread cannot be killed from here; let it finish
                # in the background. We just report cancellation.
                return make_error_response(
                    message="run_cmd: command cancelled by user.",
                    usage=zero_usage(),
                )

            # run_task finished (success or timeout)
            for t in pending:
                t.cancel()

            try:
                result = run_task.result()
            except subprocess.TimeoutExpired as e:
                log_error(
                    f"run_cmd: command timed out after {timeout}ms",
                    source="tools.py:shell(timeout)",
                )
                return make_error_response(
                    message=f"run_cmd: command timed out after {timeout}ms. "
                            "If this command is expected to take longer, retry with a larger timeout.",
                    usage=zero_usage(),
                )

            stdout_s = result.stdout or ""
            stderr_s = result.stderr or ""

            output = stdout_s
            if stderr_s:
                output += "\n" + stderr_s

            MAX_BYTES = 50 * 1024
            truncated = len(output.encode("utf-8")) > MAX_BYTES
            if truncated:
                tail = output[-MAX_BYTES:]
                output = f"...output truncated...\n\n{tail}"

            return make_success_response(
                message="Command executed.",
                data={
                    "output": output or "(no output)",
                    "returncode": result.returncode,
                    "truncated": truncated,
                    "workdir": cwd,
                },
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in run_cmd: %s", e)
            log_error(str(e), source="tools.py:shell")
            return make_error_response(
                message=f"Error executing command: {e}",
                usage=zero_usage(),
            )

    # ------------------------------------------------------------------
    # Skill tools — native, no LLM calls
    # ------------------------------------------------------------------

    async def skill(self, name: str) -> dict:
        """Load a skill by name from the skills directory.

        Reads the SKILL.md file, parses its frontmatter and body,
        and returns the skill content formatted for injection into
        the agent's context.

        Args:
            name: The skill folder name (must match a subdirectory
                  under the skills/ folder containing SKILL.md).

        Returns:
            dict with ``{status, message, data, usage}``.
            ``data`` contains the formatted skill content (XML block).
        """
        try:
            # Locate the skill folder
            skill_folder = find_skill_folder(name)
            if not skill_folder:
                return make_error_response(
                    message=f"Skill '{name}' no encontrada.",
                    usage=zero_usage(),
                )

            skill_md_path = os.path.join(skill_folder, "SKILL.md")
            if not os.path.isfile(skill_md_path):
                return make_error_response(
                    message=f"SKILL.md no existe en skill '{name}'.",
                    usage=zero_usage(),
                )

            # Parse the skill markdown
            body, reference_guide = parse_skill_md(skill_md_path)

            # Format for context injection
            from pathlib import Path
            base_dir = Path(skill_folder).as_uri()
            output = (
                f"<skill_content name=\"{name}\">\n"
                f"# Skill: {name}\n\n"
                f"{body}\n\n"
                f"Base directory for this skill: {base_dir}\n"
                f"Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.\n"
                f"Note: file list is sampled.\n\n"
                f"<skill_files>\n"
                f"{reference_guide if reference_guide else '(sin Reference Guide)'}\n"
                f"</skill_files>\n"
                f"</skill_content>"
            )

            return make_success_response(
                message=f"Skill '{name}' cargada.",
                data=output,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in skill: %s", e)
            log_error(str(e), source="tools.py:skill")
            return make_error_response(
                message=f"Error loading skill: {e}",
                usage=zero_usage(),
            )

    async def reference(self, skill: str, file: str) -> dict:
        """Load a specific reference file from a skill's directory.

        Use this when the skill's Reference Guide is large and you only
        need a specific reference file (e.g., a product catalog, API spec).

        Args:
            skill: The skill folder name.
            file: The reference filename (e.g., "products.md", "api.md",
                  or "references/drainage.md" for files in the references/ subfolder).

        Returns:
            dict with ``{status, message, data, usage}``.
            ``data`` contains the file content as plain text.
        """
        try:
            skill_folder = find_skill_folder(skill)
            if not skill_folder:
                return make_error_response(
                    message=f"Skill '{skill}' no encontrada.",
                    usage=zero_usage(),
                )

            # Try direct path first, then references/ subfolder.
            # Containment: the resolved path must stay inside skill_folder.
            # Normal names keep working unchanged. Parent references or
            # absolute paths outside the skill are rejected.
            ref_path = os.path.join(skill_folder, file)
            if not os.path.isfile(ref_path):
                # Try references/ subfolder
                ref_path = os.path.join(skill_folder, "references", file)
            try:
                base_real = os.path.realpath(skill_folder)
                target_real = os.path.realpath(ref_path)
                if target_real != base_real and not target_real.startswith(base_real + os.sep):
                    return make_error_response(
                        message=f"Referencia '{file}' fuera de la skill '{skill}'.",
                        usage=zero_usage(),
                    )
            except (OSError, ValueError) as e:
                log_error(str(e), source="tools.py:reference(containment)")
                return make_error_response(
                    message=f"Referencia '{file}' inválida en skill '{skill}'.",
                    usage=zero_usage(),
                )
            
            if not os.path.isfile(ref_path):
                return make_error_response(
                    message=f"Referencia '{file}' no existe en skill '{skill}'.",
                    usage=zero_usage(),
                )

            with open(ref_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return make_success_response(
                message=f"Referencia '{file}' de skill '{skill}' cargada.",
                data=content,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in reference: %s", e)
            log_error(str(e), source="tools.py:reference")
            return make_error_response(
                message=f"Error loading reference: {e}",
                usage=zero_usage(),
            )

    async def help(self) -> dict:
        """Read the agent's internal documentation about how it works.

        Use this tool when the user asks for help with how the agent works,
        or asks you to explain how to create tools, sub-agents, etc.

        Returns the content of the ``help.md`` file, which explains how to
        create tools, skills, agents, change models, configure the context
        window, verbose mode, etc.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            help_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "prompts",
                "help.md",
            )
            if not os.path.isfile(help_path):
                return make_error_response(
                    message="No se encontró el archivo de documentación interna (help.md).",
                    usage=zero_usage(),
                )
            with open(help_path, "r", encoding="utf-8") as f:
                content = f.read()
            return make_success_response(
                message="Documentación interna cargada.",
                data=content,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in help: %s", e)
            log_error(str(e), source="tools.py:help")
            return make_error_response(
                message=f"Error cargando documentación interna: {e}",
                usage=zero_usage(),
            )

    async def check_email(self, folder: str = "INBOX", sender: str | None = None, date: str = "1h", mark_read: bool = True) -> dict:
        """Check the IMAP mailbox for unseen emails and return them parsed.

        Connects via IMAP (SSL), searches for UNSEEN messages in the given
        folder (optionally filtered by sender and age), parses each one, and
        returns the structured results. This is a one-shot check — no polling
        loop. The agent calls this tool on demand; it does not run in the
        background.

        Args:
            folder: IMAP folder to check (default ``"INBOX"``).
            sender: Optional sender address to filter UNSEEN messages.
            date: Relative age filter: ``1h``-``23h`` (hours), ``<n>d``
                (days), ``<n>m`` (months), ``<n>y`` (years) or ``all``
                (no date filter). Default ``"1h"``.
            mark_read: When ``True`` (default) fetched messages are marked
                as read. When ``False`` they are peeked (``BODY.PEEK[]``)
                and stay unseen.

        Returns:
            dict with ``{status, message, data, usage}``.
            ``data`` contains a list of parsed emails, each with
            ``message_id``, ``sender``, ``subject``, ``date`` (raw header),
            ``date_local`` (server local time), ``body``
            and ``attachments`` (list of filenames).
        """
        try:
            cutoff, date_error = parse_relative_date(date)
            if date_error:
                return make_error_response(
                    message=date_error,
                    usage=zero_usage(),
                )

            server = os.getenv("EMAIL_IMAP_SERVER", "")
            port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
            user = os.getenv("EMAIL_USER", "")
            password = os.getenv("EMAIL_PASS", "")

            if not all([server, user, password]):
                return make_error_response(
                    message=(
                        "Faltan credenciales de email en .env "
                        "(EMAIL_IMAP_SERVER, EMAIL_USER, EMAIL_PASS)."
                    ),
                    usage=zero_usage(),
                )

            mail = imaplib.IMAP4_SSL(server, port, timeout=15)
            try:
                mail.login(user, password)
                typ_select, _ = mail.select(folder)
                if typ_select != "OK":
                    return make_error_response(
                        message=f"No se pudo seleccionar la carpeta '{folder}'.",
                        usage=zero_usage(),
                    )

                since = f' SINCE {cutoff.strftime("%d-%b-%Y")}' if cutoff else ""
                if sender:
                    search_criteria = f'(UNSEEN{since} FROM "{sender}")'
                else:
                    search_criteria = f"(UNSEEN{since})"

                typ, data = mail.search(None, search_criteria)
                if typ != "OK" or not data or not data[0]:
                    return make_success_response(
                        message="No hay mensajes no leidos.",
                        data=[],
                        usage=zero_usage(),
                    )

                msg_ids = data[0].split()
                results: list[dict] = []
                fetch_part = "(BODY[])" if mark_read else "(BODY.PEEK[])"
                for msg_id in msg_ids:
                    try:
                        typ_fetch, fetch_data = mail.fetch(msg_id, fetch_part)
                        if typ_fetch != "OK" or not fetch_data:
                            continue
                        raw_email = None
                        for item in fetch_data:
                            if isinstance(item, tuple):
                                raw_email = item[1]
                                break
                        if not raw_email:
                            continue
                        parsed = parse_email(raw_email)
                        if cutoff and is_older_than(parsed.get("date_parsed"), cutoff):
                            continue
                        results.append({
                            "message_id": parsed.get("message_id", ""),
                            "sender": parsed.get("sender", ""),
                            "subject": parsed.get("subject", ""),
                            "date": parsed.get("date", ""),
                            "date_local": parsed.get("date_local", ""),
                            "body": parsed.get("body", ""),
                            "attachments": [
                                a.get("filename", "")
                                for a in parsed.get("attachments", [])
                            ],
                        })
                    except Exception as e:
                        logger.warning("Error procesando mail %s: %s", msg_id, e)
                        log_error(str(e), source="tools.py:check_email")
                        continue
            finally:
                try:
                    mail.logout()
                except Exception as e:
                    log_error(str(e), source="tools.py:check_email(logout)")
                    pass

            return make_success_response(
                message=f"{len(results)} mensaje(s) no leido(s) encontrado(s).",
                data=results,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in check_email: %s", e)
            log_error(str(e), source="tools.py:check_email")
            return make_error_response(
                message=f"Error checking email: {e}",
                usage=zero_usage(),
            )

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Convert simple markdown text to HTML.

        Handles headers, bold, italic, links, bullet/numbered lists,
        tables and paragraph breaks. Link URLs are sanitized to block
        ``javascript:`` / ``data:`` / ``vbscript:`` schemes (XSS prevention).

        Args:
            text: The markdown text to convert.

        Returns:
            The converted HTML string.
        """
        if not text:
            return ""

        # Escape HTML entities.
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")

        # Inline: links [text](url) -> <a href="url">text</a>
        def _sanitize_url(match: re.Match) -> str:
            url = match.group(2).strip()
            label = match.group(1)
            allowed = ("http://", "https://", "mailto:", "ftp://")
            if any(url.lower().startswith(s) for s in allowed):
                return f'<a href="{url}">{label}</a>'
            if url.startswith("/") or url.startswith("#") or "." in url:
                return f'<a href="{url}">{label}</a>'
            logger.warning("Blocked unsafe URL scheme in markdown link: %s", url[:50])
            return f"{label} ({url})"

        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _sanitize_url, text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        lines = text.split("\n")
        html_lines: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]

            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                level = len(header_match.group(1))
                content = header_match.group(2)
                html_lines.append(f"<h{level}>{content}</h{level}>")
                i += 1
                continue

            if line.startswith("|") and line.endswith("|"):
                table_rows: list[str] = []
                while i < len(lines) and lines[i].startswith("|") and lines[i].endswith("|"):
                    table_rows.append(lines[i])
                    i += 1
                if table_rows:
                    html_lines.append("<table>")
                    for row_idx, row in enumerate(table_rows):
                        cells = [c.strip() for c in row.split("|")[1:-1]]
                        if cells and all(re.match(r"^[\s\-:]*$", c) for c in cells):
                            continue
                        tag = "th" if row_idx == 0 else "td"
                        html_lines.append("  <tr>")
                        for cell in cells:
                            html_lines.append(f"    <{tag}>{cell}</{tag}>")
                        html_lines.append("  </tr>")
                    html_lines.append("</table>")
                continue

            ul_match = re.match(r"^[\s]*[-*+]\s+(.+)$", line)
            if ul_match:
                html_lines.append("<ul>")
                while i < len(lines):
                    m = re.match(r"^[\s]*[-*+]\s+(.+)$", lines[i])
                    if not m:
                        break
                    html_lines.append(f"  <li>{m.group(1)}</li>")
                    i += 1
                html_lines.append("</ul>")
                continue

            ol_match = re.match(r"^[\s]*\d+\.\s+(.+)$", line)
            if ol_match:
                html_lines.append("<ol>")
                while i < len(lines):
                    m = re.match(r"^[\s]*\d+\.\s+(.+)$", lines[i])
                    if not m:
                        break
                    html_lines.append(f"  <li>{m.group(1)}</li>")
                    i += 1
                html_lines.append("</ol>")
                continue

            if not line.strip():
                html_lines.append("")
                i += 1
                continue

            html_lines.append(f"<p>{line.strip()}</p>")
            i += 1

        return "\n".join(html_lines)

    async def send_email(self, to: str, subject: str, body: str,
                         in_reply_to: str | None = None,
                         attachments: list[dict] | None = None) -> dict:
        """Send an email response via SMTP with STARTTLS.

        Reads SMTP credentials from ``.env`` (EMAIL_SMTP_SERVER,
        EMAIL_SMTP_PORT, EMAIL_USER, EMAIL_PASS). The body is markdown and
        is converted to HTML. If ``in_reply_to`` is provided, sets the
        In-Reply-To header for threading. This is a one-shot send — the
        agent calls it on demand; it does not run in the background.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body in markdown format.
            in_reply_to: Optional Message-ID of the original email being replied to.
            attachments: Optional list of ``{"filename": str, "content": bytes}`` dicts.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            

            to = (to or "").strip()
            subject = subject or ""
            body = body or ""

            if not to or "@" not in to:
                return make_error_response(
                    message=f"Direccion de destino invalida: {to!r}",
                    usage=zero_usage(),
                )

            smtp_server = os.getenv("EMAIL_SMTP_SERVER")
            raw_port = os.getenv("EMAIL_SMTP_PORT", "587")
            email_user = os.getenv("EMAIL_USER")
            email_pass = os.getenv("EMAIL_PASS")

            missing = [
                name for name, val in (
                    ("EMAIL_SMTP_SERVER", smtp_server),
                    ("EMAIL_USER", email_user),
                    ("EMAIL_PASS", email_pass),
                ) if not val
            ]
            if missing:
                return make_error_response(
                    message=f"Faltan variables de entorno: {', '.join(missing)}",
                    usage=zero_usage(),
                )

            try:
                smtp_port = int(raw_port)
                if not (1 <= smtp_port <= 65535):
                    raise ValueError()
            except (ValueError, TypeError) as e:
                log_error(str(e), source="tools.py:_smtp_send(port)")
                smtp_port = 587

            has_attachments = bool(attachments)
            if has_attachments:
                outer_msg = MIMEMultipart("mixed")
                msg = MIMEMultipart("alternative")
                outer_msg.attach(msg)
            else:
                outer_msg = MIMEMultipart("alternative")
                msg = outer_msg

            outer_msg["From"] = email_user
            outer_msg["To"] = to
            outer_msg["Subject"] = subject.replace("\n", " ").replace("\r", " ")
            outer_msg["Date"] = formatdate(localtime=True)
            outer_msg["Message-ID"] = make_msgid()

            if in_reply_to:
                outer_msg["In-Reply-To"] = in_reply_to
                outer_msg["References"] = in_reply_to

            html_body = Tools._markdown_to_html(body)
            html_content = (
                "<html>\n<head></head>\n<body>\n"
                f"    {html_body}\n"
                "</body>\n</html>"
            )
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            if has_attachments:
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        continue
                    filename = attachment.get("filename", "attachment")
                    content = attachment.get("content")
                    if content is None:
                        continue
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(content)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition", "attachment", filename=filename
                    )
                    outer_msg.attach(part)

            def _smtp_send() -> None:
                server = None
                try:
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(email_user, email_pass)
                    server.sendmail(email_user, [to], outer_msg.as_string())
                finally:
                    if server:
                        try:
                            server.quit()
                        except Exception as e:
                            log_error(str(e), source="tools.py:_smtp_send(quit)")
                            pass

            await asyncio.to_thread(_smtp_send)

            return make_success_response(
                message=f"Email enviado a {to}",
                data={"to": to, "subject": subject},
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in send_email: %s", e)
            log_error(str(e), source="tools.py:_smtp_send")
            return make_error_response(
                message=f"Error enviando email: {e}",
                usage=zero_usage(),
            )

    async def list_dir(self, path: str = ".") -> dict:
        """List files and directories in a given path.

        Args:
            path: Directory path to list. Defaults to current working directory.

        Returns:
            dict with ``{status, message, data, usage}``.
        """
        try:
            # Normalize path: on Windows, drive-relative paths like "D:/" or "D:"
            # resolve to the current working directory on that drive, not the root.
            # We need to explicitly convert them to the actual root "D:\\".
            if os.name == "nt":
                # Match "D:/" or "D:" (drive letter + optional slash)
                if re.match(r'^[A-Za-z]:/?$', path):
                    search = path.rstrip("/") + "\\"
                else:
                    search = os.path.abspath(path)
            else:
                search = os.path.abspath(path)

            if not os.path.isdir(search):
                return make_error_response(
                    message=f"The path must be a directory: {search}",
                    usage=zero_usage(),
                )

            entries = os.listdir(search)
            items = []
            for entry in sorted(entries):
                full = os.path.join(search, entry)
                item_type = "dir" if os.path.isdir(full) else "file"
                items.append({"name": entry, "type": item_type})

            if not items:
                return make_success_response(
                    message="Directory is empty.",
                    data=[],
                    usage=zero_usage(),
                )

            return make_success_response(
                message=f"{len(items)} entradas encontradas en {search}.",
                data=items,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in list_dir: %s", e)
            log_error(str(e), source="tools.py:list_dir")
            return make_error_response(
                message=f"Error listing directory: {e}",
                usage=zero_usage(),
            )

    async def query_model_capabilities(self, provider: str, model: str) -> dict:
        """Query model capabilities from the local catalog without huge context.

        Thin wrapper over ``GET /config/models/capabilities``: calls the
        endpoint function in-process and returns its payload under the
        unified contract, so creator agents can validate frontmatter
        parameters instead of inventing them.

        Args:
            provider: Provider name (e.g. ``"openrouter"``,
                ``"google"``, ``"LOCAL"``).
            model: Model identifier (e.g. ``"qwen/qwen3-32b"``).

        Returns:
            dict with ``{status, message, data, usage}``. On success,
            ``data`` holds the endpoint payload (``reasoning_supported``,
            ``reasoning_options``, ``reasoning_type``,
            ``response_format_supported``, ``temperature_supported``,
            ``tool_call_supported``, ``found``, ...).
        """
        try:
            prov = (provider or "").strip()
            model_id = (model or "").strip()
            if not prov or not model_id:
                return make_error_response(
                    message="Provider and model are required.",
                    usage=zero_usage(),
                )

            from backend.routes.config import (
                get_model_capabilities as capabilities_endpoint,
            )

            resp = await capabilities_endpoint(model=model_id, provider=prov)
            payload = json.loads(resp.body.decode("utf-8"))
            if resp.status_code != 200 or payload.get("status") != "success":
                return make_error_response(
                    message=payload.get("message", "Error querying capabilities."),
                    usage=zero_usage(),
                )
            if payload.get("found") is False:
                return make_error_response(
                    message=(
                        f"Model '{model_id}' not found for provider "
                        f"'{prov}' in the local catalog."
                    ),
                    usage=zero_usage(),
                )
            return make_success_response(
                message=f"Capabilities for '{prov}/{model_id}'.",
                data=payload,
                usage=zero_usage(),
            )
        except Exception as e:
            logger.exception("Error in query_model_capabilities: %s", e)
            log_error(str(e), source="tools.py:query_model_capabilities")
            return make_error_response(
                message=f"Error querying model capabilities: {e}",
                usage=zero_usage(),
            )

if __name__ == '__main__':
    print(f'Tools module — {len(Tools().tools_registry())} tools registradas.')
    for r in Tools().tools_registry():
        print(f'  - {r["name"]}')
