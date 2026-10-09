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

Refactored as a package: this module keeps the central registry/dispatch
(``ToolsBase``) and composes the 18 native tools from individual modules
(``read.py``, ``write.py``, ...) via mixins. ``Tools`` preserves the
original public API (``from backend.agent.tools import Tools``).
"""

import importlib
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import time
import types

_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.permissions import (
    filter_tools,
    get_agent_prompt,
    get_skill_permissions,
    get_tool_permissions,
    get_agent_parameters,
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

from backend.agent.tools.check_email import CheckEmailMixin
from backend.agent.tools.edit import EditMixin
from backend.agent.tools.glob import GlobMixin
from backend.agent.tools.grep import GrepMixin
from backend.agent.tools.help import HelpMixin
from backend.agent.tools.list_dir import ListDirMixin
from backend.agent.tools.query_model_capabilities import QueryModelCapabilitiesMixin
from backend.agent.tools.rag import RagMixin
from backend.agent.tools.read import ReadMixin
from backend.agent.tools.reference import ReferenceMixin
from backend.agent.tools.search_memory import SearchMemoryMixin
from backend.agent.tools.send_email import SendEmailMixin
from backend.agent.tools.shell import ShellMixin
from backend.agent.tools.skill import SkillMixin
from backend.agent.tools.task import TaskMixin
from backend.agent.tools.webfetch import WebfetchMixin
from backend.agent.tools.websearch import WebsearchMixin
from backend.agent.tools.write import WriteMixin


logger = logging.getLogger(__name__)


class ToolsBase:
    """Central registry and dispatch for agent tools."""

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


class Tools(
    CheckEmailMixin,
    EditMixin,
    GlobMixin,
    GrepMixin,
    HelpMixin,
    ListDirMixin,
    QueryModelCapabilitiesMixin,
    RagMixin,
    ReadMixin,
    ReferenceMixin,
    SearchMemoryMixin,
    SendEmailMixin,
    ShellMixin,
    SkillMixin,
    TaskMixin,
    WebfetchMixin,
    WebsearchMixin,
    WriteMixin,
    ToolsBase,
):
    """Tools for the quotation agent.

    Each method implements a step of the quotation pipeline and
    returns a dictionary with the unified contract ``{status, message, data, usage}``.

    The ``registry`` property automatically exposes LLM-callable tools by scanning
    the class for public methods (no leading underscore). For each method it derives:

    * ``name`` — the method name
    * ``description`` — the first line of the docstring
    * ``parameters`` — JSON Schema inferred from the method signature (type hints + defaults)
    """


if __name__ == '__main__':
    print(f'Tools module — {len(Tools().tools_registry())} tools registradas.')
    for r in Tools().tools_registry():
        print(f'  - {r["name"]}')
