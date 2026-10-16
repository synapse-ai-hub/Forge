"""Tool-call normalization between the internal format and each provider's format."""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.agent.utils.error_logger import log_error

class ToolCallsMixin:
    """Converts tool calls to and from the provider wire format."""

    def _normalize_tool_calls(self, tool_calls: list[Any] | None) -> list[dict[str, Any]] | None:
        """Normalize raw tool_calls to uniform ``{"id", "name", "args"}``.

        Args:
            tool_calls: Raw tool_calls from the API (OpenAI-compatible or Ollama format).

        Returns:
            Normalized list, or ``None`` if empty.
        """
        if not tool_calls:
            return None
        normalized = []
        for tc in tool_calls:
            entry: dict[str, Any] = {}
            # Gemini style dict built in the GOOGLE branch:
            # {"name", "args", "signature"}.
            if isinstance(tc, dict):
                entry["id"] = f"call_{uuid.uuid4().hex}"
                entry["name"] = tc.get("name") or ""
                args = tc.get("args")
                entry["args"] = args if isinstance(args, dict) else {}
                if tc.get("signature"):
                    entry["thought_signature"] = tc["signature"]
                normalized.append(entry)
                continue
            # Gemini FunctionCall style: name/args directly on the object,
            # no id and no nested function attribute.
            if not hasattr(tc, "function"):
                try:
                    entry["id"] = f"call_{uuid.uuid4().hex}"
                    entry["name"] = tc.name
                except AttributeError as e:
                    log_error(str(e), source="agent.py:_normalize_tool_calls(gemini)")
                    continue
                args = getattr(tc, "args", None)
                entry["args"] = args if isinstance(args, dict) else {}
                normalized.append(entry)
                continue
            try:
                entry["id"] = tc.id
            except AttributeError as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(id)")
                entry["id"] = ""
            # OpenAI-compatible APIs always provide an id; Ollama may omit it. Generate one so
            # the assistant message and the tool result stay linked.
            if not entry["id"]:
                entry["id"] = f"call_{uuid.uuid4().hex}"
            try:
                entry["name"] = tc.function.name
            except AttributeError as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(name)")
                continue
            try:
                args_raw = tc.function.arguments
                if isinstance(args_raw, str):
                    entry["args"] = json.loads(args_raw) if args_raw else {}
                elif isinstance(args_raw, dict):
                    entry["args"] = args_raw
                else:
                    entry["args"] = {}
            except (AttributeError, json.JSONDecodeError) as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(args)")
                entry["args"] = {}
            normalized.append(entry)
        return normalized if normalized else None

    def _to_provider_tool_calls(
        self, tool_calls: list[dict[str, Any]], is_openai_compatible: bool
    ) -> list[dict[str, Any]]:
        """Convert normalized tool_calls to the SDK format each provider expects.

        Normalized tool_calls have the shape
        ``{"id", "name", "args"}``. Both OpenAI-compatible providers
        and Ollama expect the wrapped shape
        ``{"id", "type": "function", "function": {"name", "arguments"}}``,
        but they differ in how ``arguments`` is encoded:

        - **OpenAI-compatible**: ``function.arguments`` must be a **JSON string**.
        - **Ollama**: ``function.arguments`` must be a **dict**.

        Args:
            tool_calls: Normalized list (``{"id", "name", "args"}``) or a
                list that is already in SDK format (has a ``function`` key).
            is_openai_compatible: ``True`` for OpenAI-compatible providers,
                ``False`` for Ollama.

        Returns:
            List of tool_calls in the provider's expected format.
        """
        out: list[dict[str, Any]] = []
        for tc in tool_calls:
           
            # the arguments encoding for the current provider.
            if "function" in tc:
                func = dict(tc["function"])
                args = func.get("arguments")
                if is_openai_compatible and isinstance(args, dict):
                    func["arguments"] = json.dumps(args, ensure_ascii=False)
                elif not is_openai_compatible and isinstance(args, str):
                    try:
                        func["arguments"] = json.loads(args)
                    except (json.JSONDecodeError, TypeError) as e:
                        log_error(str(e), source="agent.py:_to_provider_tool_calls(func_args)")
                out.append(
                    {
                        "id": tc.get("id") or f"call_{uuid.uuid4().hex}",
                        "type": "function",
                        "function": func,
                    }
                )
                continue
            # Normalized format: {"id", "name", "args"}
            tc_id = tc.get("id") or f"call_{uuid.uuid4().hex}"
            args = tc.get("args", {})
            if is_openai_compatible:
                try:
                    func_args = json.dumps(args, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    log_error(str(e), source="agent.py:_to_provider_tool_calls(func_args)")
                    func_args = json.dumps({}, ensure_ascii=False)
            else:
                func_args = args
            out.append(
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": func_args,
                    }
                }
            )
        return out
